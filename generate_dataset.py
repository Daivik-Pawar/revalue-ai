"""Generate the SYNTHETIC resale-price datasets for ReValue AI.

IMPORTANT: every price produced here is synthetic. It comes from the
depreciation rules written below plus random noise, NOT from real market
sales. Models trained on it show that the software pipeline works; they say
nothing about accuracy on real market prices. Replace the CSVs in dataset/
with real completed-sale data when it is available.

Design rules:
  * The hidden "new price" anchor is used to build the target but is never
    written to the CSVs (no target proxy column, no leakage).
  * Each row carries price_type = completed_sale or asking. Asking prices are
    inflated versions of the same rule so the pipeline can demonstrate the
    difference; training should use completed_sale rows only.
  * Fixed seed, so the output is identical on every run.

Run:  python generate_dataset.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tiers import CPU_ANCHOR, CPU_TIER, DGPU_TIER, GPU_ANCHOR, STORAGE_GB

SEED = 42
CURRENT_YEAR = 2026
ROOT = Path(__file__).parent
OUT = ROOT / "dataset"
rng = np.random.default_rng(SEED)

# Part tiers (CPU_TIER, DGPU_TIER, CPU_ANCHOR, GPU_ANCHOR) and STORAGE_GB live in
# tiers.py so the Flask app uses exactly the same values.

# ---------------------------------------------------------------------------
# Shared condition / age / accessory sampling and price multipliers.
# ---------------------------------------------------------------------------
PHYS = ["Like new", "Good (light wear)", "Fair (visible wear)", "Poor (heavy wear)"]
PHYS_MULT = dict(zip(PHYS, [1.00, 0.93, 0.82, 0.65]))
WORK = ["Fully working", "Works with minor issues", "Not working"]
WORK_MULT = dict(zip(WORK, [1.00, 0.85, 0.35]))


def sample_age():
    return int(np.clip(rng.gamma(shape=2.2, scale=1.6), 0, 12))


def sample_condition(age, has_battery=False):
    """Older items are more likely to be worn, repaired or faulty."""
    wear = min(age / 10, 1.0)
    p_phys = np.array([0.35 - 0.25 * wear, 0.40, 0.20 + 0.15 * wear, 0.05 + 0.10 * wear])
    p_phys = np.clip(p_phys, 0.02, None); p_phys /= p_phys.sum()
    phys = rng.choice(PHYS, p=p_phys)
    p_work = np.array([0.88 - 0.20 * wear, 0.09 + 0.12 * wear, 0.03 + 0.08 * wear])
    p_work /= p_work.sum()
    work = rng.choice(WORK, p=p_work)
    warranty = bool(age <= 3 and rng.random() < (0.65 if age <= 1 else 0.30))
    row = {
        "purchase_year": CURRENT_YEAR - age,
        "age_years": age,
        "physical_condition": phys,
        "working_status": work,
        "repair_history": "Yes" if rng.random() < 0.08 + 0.18 * wear else "No",
        "warranty_available": "Yes" if warranty else "No",
        "warranty_left": rng.choice(["Under 3 months", "3 to 6 months", "6 to 12 months", "More than 12 months"]) if warranty else np.nan,
        "original_box": "Yes" if rng.random() < 0.45 else "No",
        "purchase_bill": "Yes" if rng.random() < 0.40 else "No",
    }
    return row


WARRANTY_BONUS = {"Under 3 months": 0.01, "3 to 6 months": 0.02, "6 to 12 months": 0.035, "More than 12 months": 0.05}


def condition_multiplier(row, issue_penalty=0.0):
    m = PHYS_MULT[row["physical_condition"]] * WORK_MULT[row["working_status"]]
    m *= 0.95 if row["repair_history"] == "Yes" else 1.0
    if row["warranty_available"] == "Yes":
        m *= 1.0 + WARRANTY_BONUS[row["warranty_left"]]
    m *= 1.02 if row["original_box"] == "Yes" else 1.0
    m *= 1.02 if row["purchase_bill"] == "Yes" else 1.0
    m *= max(0.4, 1.0 - issue_penalty)
    return m


def finish(new_price, retention_rate, floor, row, brand_ret=1.0, issue_penalty=0.0, noise=0.06, extra=1.0):
    age = row["age_years"]
    retention = max(floor, np.exp(-retention_rate * age)) * brand_ret
    retention = min(retention, 0.97)
    price = new_price * retention * condition_multiplier(row, issue_penalty) * extra
    price *= float(np.exp(rng.normal(0, noise)))
    return max(100.0, round(price / 50) * 50)


def tag_price_type(df):
    df = df.copy()
    is_ask = rng.random(len(df)) < 0.15
    df["price_type"] = np.where(is_ask, "asking", "completed_sale")
    infl = rng.uniform(1.08, 1.25, len(df))
    df["resale_price_inr"] = np.where(is_ask, (df["resale_price_inr"] * infl / 50).round() * 50, df["resale_price_inr"])
    df["data_source"] = "synthetic_v1"
    df.insert(0, "row_id", np.arange(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# Laptops: rows follow the models and options in data/laptops.json.
# ---------------------------------------------------------------------------
LAPTOP_ISSUES = {"display_damage": 0.10, "battery_issue": 0.07, "keyboard_trackpad_issue": 0.05,
                 "charging_issue": 0.05, "other_hw_issue": 0.04}
BATTERY = ["Above 80%", "60% to 80%", "Below 60%", "Not sure"]
BATTERY_MULT = dict(zip(BATTERY, [1.00, 0.93, 0.85, 0.95]))


def laptop_configs():
    data = json.load(open(ROOT / "data" / "laptops.json", encoding="utf-8"))
    gfx = json.load(open(ROOT / "data" / "graphics.json", encoding="utf-8"))
    vram = {g["name"]: g["vram_gb"] for g in gfx["dedicated"]}
    for brand in data["brands"]:
        for m in brand["models"]:
            yield brand["name"], m, vram


def make_laptops(n):
    models = list(laptop_configs())
    rows = []
    for _ in range(n):
        brand, m, vram = models[rng.integers(len(models))]
        if m.get("verified"):
            v = dict(m["variants"][0])
        else:
            o = m["variant_options"]
            v = {"cpu": rng.choice(o["cpu"]), "ram_capacity_gb": int(rng.choice(o["ram_capacity_gb"])),
                 "storage_capacity": rng.choice(o["storage_capacity"])}
            if "dgpu_model" in o:
                v["dgpu_model"] = rng.choice(o["dgpu_model"])
                v["dgpu_vram_gb"] = int(rng.choice(vram[v["dgpu_model"]]))
                v["graphics_type"] = "both"
            else:
                v["graphics_type"] = "integrated"
            v["ram_type"] = "DDR4" if brand != "Apple" else "Unified"
        dgpu = v.get("dgpu_model")
        age = sample_age()
        row = sample_condition(age)
        issues = {k: int(rng.random() < p * (1 + age / 8)) for k, p in LAPTOP_ISSUES.items()}
        battery = rng.choice(BATTERY, p=[0.45 - 0.03 * min(age, 6), 0.30, 0.15 + 0.03 * min(age, 6), 0.10])
        storage_gb = STORAGE_GB[v["storage_capacity"]]
        cpu_t = CPU_TIER[v["cpu"]]
        gpu_t = DGPU_TIER.get(dgpu, 0.0)
        # hidden new-price anchor (rupees, illustrative)
        segment = 80000 if brand == "Apple" else (34000 if gpu_t == 0 else 52000)
        new_price = segment + cpu_t * 7000 + (v["ram_capacity_gb"] - 8) * 1200 + storage_gb / 256 * 2200 + gpu_t * 8500
        issue_pen = 0.08 * issues["display_damage"] + 0.06 * issues["battery_issue"] + 0.04 * issues["keyboard_trackpad_issue"] \
            + 0.04 * issues["charging_issue"] + 0.07 * issues["other_hw_issue"]
        row["original_charger"] = "Yes" if rng.random() < 0.80 else "No"
        extra = BATTERY_MULT[battery] * (1.0 if row["original_charger"] == "Yes" else 0.94)
        price = finish(new_price, 0.20, 0.12, row, brand_ret=1.25 if brand == "Apple" else 1.0,
                       issue_penalty=issue_pen, extra=extra)
        rows.append({
            "brand": brand, "model_id": m["id"], "cpu": v["cpu"], "cpu_tier": cpu_t,
            "ram_capacity_gb": v["ram_capacity_gb"], "storage_gb": storage_gb,
            "graphics_type": v["graphics_type"], "dgpu_model": dgpu if dgpu else "None",
            "dgpu_tier": gpu_t, "dgpu_vram_gb": v.get("dgpu_vram_gb", 0),
            "battery_health": battery, **issues, **row, "resale_price_inr": price,
        })
    return tag_price_type(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Desktops
# ---------------------------------------------------------------------------
def make_desktops(n):
    rows = []
    for _ in range(n):
        kind = rng.choice(["branded_pc", "custom_pc"], p=[0.45, 0.55])
        brand = rng.choice(["Dell", "HP", "Lenovo", "Acer", "ASUS"]) if kind == "branded_pc" else "Custom build"
        cpu_t = float(rng.choice([1.8, 2.5, 3.0, 3.5, 4.0, 4.5]))
        ram = int(rng.choice([4, 8, 16, 32]))
        storage = int(rng.choice([256, 512, 1000, 2000]))
        has_gpu = rng.random() < (0.35 if kind == "branded_pc" else 0.8)
        gpu_t = float(rng.choice([1.5, 2.5, 3.3, 3.8, 4.5])) if has_gpu else 0.0
        psu = int(rng.choice([450, 550, 650, 750])) if kind == "custom_pc" else 0
        age = sample_age()
        row = sample_condition(age)
        new_price = 18000 + cpu_t * 7500 + (ram - 8) * 900 + storage / 256 * 1800 + gpu_t * 9500 + psu / 100 * 300
        reported_issue = int(rng.random() < 0.08 + age / 40)
        price = finish(new_price, 0.17, 0.12, row, issue_penalty=0.05 * reported_issue)
        rows.append({"reported_issue": reported_issue, "desktop_type": kind, "brand": brand, "cpu_tier": cpu_t, "ram_capacity_gb": ram,
                     "storage_gb": storage, "has_dedicated_gpu": int(has_gpu), "gpu_tier": gpu_t,
                     "psu_wattage": psu, **row, "resale_price_inr": price})
    return tag_price_type(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Individual components. Anchors (CPU_ANCHOR, GPU_ANCHOR in tiers.py) are rough
# illustrative launch-price levels.
# ---------------------------------------------------------------------------
COMP_BRANDS = {"gpu": ["ASUS", "MSI", "Gigabyte", "Zotac", "Palit", "Sapphire", "XFX"],
               "ram": ["Corsair", "Kingston", "G.Skill", "Crucial", "Adata"],
               "ssd": ["Samsung", "WD", "Crucial", "Kingston", "Adata"],
               "hdd": ["Seagate", "WD", "Toshiba"],
               "motherboard": ["ASUS", "MSI", "Gigabyte", "ASRock"],
               "psu": ["Corsair", "Cooler Master", "Antec", "Deepcool", "Cosmic Byte"],
               "cooler": ["Cooler Master", "Deepcool", "Noctua", "Corsair"],
               "cabinet": ["Ant Esports", "Cooler Master", "NZXT", "Deepcool"],
               "expansion_card": ["TP-Link", "ASUS", "Gigabyte"]}
COMP_KEYS = ["subtype", "brand", "model_name", "spec_tier", "capacity", "generation", "variant"]


def make_components(n):
    kinds = ["cpu", "gpu", "ram", "ssd", "hdd", "motherboard", "psu", "cooler", "cabinet", "expansion_card"]
    w = np.array([1.3, 1.5, 1.4, 1.2, 0.8, 0.9, 0.9, 0.6, 0.6, 0.4]); w /= w.sum()
    rows = []
    for _ in range(n):
        k = rng.choice(kinds, p=w)
        age = sample_age()
        row = sample_condition(age)
        rec = {"subtype": k, "brand": "", "model_name": "", "spec_tier": 0.0, "capacity": 0, "generation": "", "variant": "",
               "reported_issue": 0}

        def issue(p, weight):
            """Draw the fault flag, remember it as a column, return its price penalty."""
            flag = int(rng.random() < p)
            rec["reported_issue"] = flag
            return weight * flag

        if k == "cpu":
            name = rng.choice(list(CPU_ANCHOR)); base, tier = CPU_ANCHOR[name]
            rec.update(brand="Intel" if "Intel" in name else "AMD", model_name=name, spec_tier=tier,
                       generation="AM5" if "7600" in name or "7700X" in name else ("LGA1700" if "Intel" in name else "AM4"))
            price = finish(base, 0.22, 0.10, row, issue_penalty=issue(0.05, 0.05))
        elif k == "gpu":
            name = rng.choice(list(GPU_ANCHOR)); base, tier = GPU_ANCHOR[name]
            vram = int(rng.choice({"GTX 1650": [4], "1660": [6], "3050": [6, 8], "3060": [8, 12], "4060 Ti": [8, 16], "4060": [8],
                                   "580": [4, 8], "6600": [8]}[next(s for s in ["4060 Ti", "GTX 1650", "1660", "3050", "3060", "4060", "580", "6600"] if s in name)]))
            mined = int(rng.random() < 0.06)
            rec.update(brand=rng.choice(COMP_BRANDS["gpu"]), model_name=name, spec_tier=tier, capacity=vram, generation="GDDR6" if "580" not in name else "GDDR5")
            price = finish(base * (1 + (vram - 8) * 0.02), 0.25, 0.10, row, issue_penalty=0.15 * mined + issue(0.06, 0.06))
            rec["variant"] = "heavily_mined" if mined else "normal_use"
        elif k == "ram":
            cap = int(rng.choice([4, 8, 16, 32])); ddr = rng.choice(["DDR3", "DDR4", "DDR5"], p=[0.2, 0.5, 0.3])
            mods = int(rng.choice([1, 2], p=[0.6, 0.4])); form = rng.choice(["DIMM", "SO-DIMM"], p=[0.6, 0.4])
            rate = {"DDR3": 220, "DDR4": 320, "DDR5": 480}[ddr]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), spec_tier={"DDR3": 1.0, "DDR4": 2.0, "DDR5": 3.0}[ddr], capacity=cap * mods,
                       generation=ddr, variant=f"{form}_{mods}x{cap}")
            price = finish(cap * mods * rate, 0.24, 0.12, row, issue_penalty=issue(0.03, 0.1))
        elif k in ("ssd", "hdd"):
            cap = int(rng.choice([120, 240, 256, 480, 512, 960, 1000, 2000]) if k == "ssd" else rng.choice([320, 500, 1000, 2000, 4000]))
            if k == "ssd":
                iface = rng.choice(["SATA", "NVMe PCIe 3.0", "NVMe PCIe 4.0"], p=[0.4, 0.4, 0.2])
                rate = {"SATA": 4.2, "NVMe PCIe 3.0": 5.0, "NVMe PCIe 4.0": 6.5}[iface]
                rec.update(generation=iface, spec_tier={"SATA": 1.0, "NVMe PCIe 3.0": 2.0, "NVMe PCIe 4.0": 3.0}[iface])
                price = finish(cap * rate + 600, 0.22, 0.10, row, issue_penalty=issue(0.05, 0.2))
            else:
                rpm = int(rng.choice([5400, 7200], p=[0.5, 0.5]))
                rec.update(generation=f"{rpm}rpm", spec_tier=1.0 if rpm == 5400 else 1.3)
                price = finish(cap * 2.2 + 1200, 0.28, 0.08, row, issue_penalty=issue(0.08 + age / 40, 0.25))
            rec.update(brand=rng.choice(COMP_BRANDS[k]), capacity=cap)
        elif k == "motherboard":
            gen = rng.choice(["AM4", "AM5", "LGA1200", "LGA1700"], p=[0.3, 0.2, 0.2, 0.3]); ff = rng.choice(["ATX", "Micro-ATX", "Mini-ITX"], p=[0.4, 0.5, 0.1])
            tier = {"AM4": 2.0, "AM5": 3.5, "LGA1200": 2.0, "LGA1700": 3.0}[gen]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), spec_tier=tier, generation=gen, variant=ff)
            price = finish(6000 + tier * 4500 + (1500 if ff == "ATX" else 0), 0.20, 0.12, row, issue_penalty=issue(0.05, 0.2))
        elif k == "psu":
            w_ = int(rng.choice([450, 550, 650, 750, 850])); eff = rng.choice(["80+ White", "80+ Bronze", "80+ Gold"], p=[0.2, 0.55, 0.25])
            tier = {"80+ White": 1.0, "80+ Bronze": 2.0, "80+ Gold": 3.0}[eff]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), spec_tier=tier, capacity=w_, generation=eff)
            price = finish(w_ * 5.5 + tier * 1200, 0.18, 0.12, row, issue_penalty=issue(0.04, 0.15))
        elif k == "cooler":
            t = rng.choice(["Air cooler", "AIO 240 mm", "AIO 360 mm"], p=[0.6, 0.3, 0.1]); base = {"Air cooler": 2500, "AIO 240 mm": 7500, "AIO 360 mm": 11000}[t]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), variant=t, spec_tier={"Air cooler": 1.0, "AIO 240 mm": 2.0, "AIO 360 mm": 3.0}[t])
            price = finish(base, 0.22, 0.10, row, issue_penalty=issue(0.05, 0.1))
        elif k == "cabinet":
            size = rng.choice(["Micro-ATX", "Mid tower", "Full tower"], p=[0.25, 0.65, 0.10]); base = {"Micro-ATX": 3000, "Mid tower": 4500, "Full tower": 9000}[size]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), variant=size, spec_tier={"Micro-ATX": 1.0, "Mid tower": 2.0, "Full tower": 3.0}[size])
            price = finish(base, 0.12, 0.15, row, issue_penalty=issue(0.06, 0.1))
        else:
            t = rng.choice(["Wi-Fi card", "Ethernet card", "Sound card"], p=[0.5, 0.3, 0.2]); base = {"Wi-Fi card": 1800, "Ethernet card": 1200, "Sound card": 2500}[t]
            rec.update(brand=rng.choice(COMP_BRANDS[k]), variant=t, spec_tier=1.0)
            price = finish(base, 0.25, 0.10, row)
        rows.append({**rec, **row, "resale_price_inr": price})
    return tag_price_type(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Monitors
# ---------------------------------------------------------------------------
def make_monitors(n):
    rows = []
    for _ in range(n):
        size = float(rng.choice([21.5, 24, 27, 32, 34], p=[0.2, 0.4, 0.25, 0.1, 0.05]))
        res = rng.choice(["1920x1080", "2560x1440", "3840x2160", "3440x1440"], p=[0.6, 0.25, 0.1, 0.05])
        hz = int(rng.choice([60, 75, 100, 144, 165], p=[0.35, 0.2, 0.1, 0.25, 0.1]))
        panel = rng.choice(["IPS", "VA", "TN"], p=[0.6, 0.25, 0.15])
        curved = rng.random() < 0.15
        brand = rng.choice(["Dell", "LG", "Samsung", "BenQ", "Acer", "ASUS", "HP", "MSI"])
        age = sample_age(); row = sample_condition(age)
        px = {"1920x1080": 1.0, "2560x1440": 1.9, "3840x2160": 3.4, "3440x1440": 2.5}[res]
        new_price = 4500 + size * 260 * px + (hz - 60) * 55 + {"IPS": 1500, "VA": 700, "TN": 0}[panel] + (1200 if curved else 0)
        dead = int(rng.random() < 0.05 + age / 50); bleed = int(rng.random() < 0.06 + age / 60)
        price = finish(new_price, 0.17, 0.12, row, issue_penalty=0.12 * dead + 0.05 * bleed)
        rows.append({"brand": brand, "size_in": size, "resolution": res, "refresh_rate_hz": hz, "panel": panel,
                     "curved": int(curved), "dead_pixels": dead, "backlight_bleed": bleed, **row, "resale_price_inr": price})
    return tag_price_type(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Peripherals: keyboards, mice and other accessories share one table.
# ---------------------------------------------------------------------------
PERIPHERAL_BASE = {  # subtype: (illustrative new price at tier 1, step per tier, retention rate)
    "keyboard": (900, 1400, 0.22), "mouse": (500, 900, 0.22), "charger": (1500, 900, 0.20), "cable": (250, 250, 0.35),
    "headset": (1200, 1600, 0.25), "webcam": (1000, 1500, 0.22), "external_storage": (2500, 1800, 0.20),
    "hub_dock": (800, 2200, 0.22), "cooling_pad": (900, 700, 0.25),
}
SUBTYPE_OPTIONS = {"keyboard": ["Office / membrane", "Mechanical", "Gaming", "Wireless"], "mouse": ["Office wired", "Office wireless", "Gaming wired", "Gaming wireless"],
                   "charger": ["USB-C", "Barrel (round pin)"], "cable": ["HDMI", "DisplayPort", "USB-C", "Ethernet (LAN)", "SATA"],
                   "headset": ["3.5 mm wired", "USB wired", "Bluetooth"], "webcam": ["720p", "1080p", "4K"],
                   "external_storage": ["External HDD", "External SSD"], "hub_dock": ["USB hub", "USB-C multiport hub", "Docking station"],
                   "cooling_pad": ["Standard"]}


def make_peripherals(n):
    kinds = list(PERIPHERAL_BASE); rows = []
    for _ in range(n):
        k = rng.choice(kinds); base, step, ret = PERIPHERAL_BASE[k]
        opt = rng.choice(SUBTYPE_OPTIONS[k]); tier = int(rng.choice([1, 2, 3], p=[0.5, 0.35, 0.15]))
        brand = rng.choice(["Logitech", "HP", "Dell", "Redragon", "Razer", "Corsair", "Zebronics", "Ant Esports", "Anker", "Generic"])
        wireless = int(any(s in opt for s in ["wireless", "Wireless", "Bluetooth"]))
        cap = int(rng.choice([500, 1000, 2000])) if k == "external_storage" else 0
        age = sample_age(); row = sample_condition(age)
        new_price = base + (tier - 1) * step + wireless * 500 + (1500 if opt in ("Mechanical", "4K", "Docking station", "External SSD") else 0) + cap * 1.4
        reported_issue = int(rng.random() < 0.07 + age / 50)
        price = finish(new_price, ret, 0.08, row, issue_penalty=0.1 * reported_issue)
        rows.append({"reported_issue": reported_issue, "subtype": k, "brand": brand, "type_option": opt, "tier": tier, "wireless": wireless,
                     "capacity_gb": cap, **row, "resale_price_inr": price})
    return tag_price_type(pd.DataFrame(rows))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    tables = {"laptops": make_laptops(1500), "desktops": make_desktops(400), "components": make_components(1400),
              "monitors": make_monitors(450), "peripherals": make_peripherals(600)}
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:12s} {len(df):5d} rows  {df.shape[1]:2d} cols  "
              f"median price (completed) = {df.loc[df.price_type == 'completed_sale', 'resale_price_inr'].median():,.0f}")
