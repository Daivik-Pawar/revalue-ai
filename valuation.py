"""Turn a user's form answers into an ML price estimate.

Flow: validate -> fill known model specs -> map answers to the raw columns the
model was trained on -> engineer_features (same code as training) -> predict.
The price always comes from the trained model in model/resale_model.pkl.
Nothing here hardcodes a price.
"""
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import catalog
from preprocess import engineer_features
from tiers import (CPU_ANCHOR, CPU_TIER, DGPU_TIER, GPU_ANCHOR, STORAGE_GB, cpu_tier_from_text,
                   gpu_tier_from_text)

ROOT = Path(__file__).parent
CURRENT_YEAR = 2026
MAX_TRAIN_AGE = 12

DISCLAIMER = ("This is an estimated resale value predicted by a machine-learning model. It is not a guaranteed "
              "selling price, and nothing is bought or sold through this website.")


class UnsupportedProduct(Exception):
    """Raised for product types that have no trained model yet."""


_bundle = None
_metrics = None


def bundle():
    global _bundle
    if _bundle is None:
        _bundle = joblib.load(ROOT / "model" / "resale_model.pkl")
    return _bundle


def metrics():
    global _metrics
    if _metrics is None:
        with open(ROOT / "model" / "metrics.json", encoding="utf-8") as f:
            _metrics = json.load(f)
    return _metrics


def group_for(category, subtype):
    """Which trained model serves a product type, or None."""
    if category == "laptops":
        return "laptops"
    if category == "desktops":
        return "desktops"
    if category == "monitors":
        return "monitors"
    if category == "components" and subtype != "other_component":
        return "components"
    if category in ("keyboards_mice", "accessories") and subtype != "other_accessory":
        return "peripherals"
    return None


# ------------------------------------------------------------------ small helpers
def num(v):
    if v is None or (isinstance(v, str) and v.strip().lower() in ("", "unknown", "other")):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def known(v):
    return not catalog.is_unknown(v)


def storage_gb(text):
    """Total gigabytes in a text like '512 GB', '1 TB' or '256 GB SSD + 1 TB HDD'."""
    if not known(text):
        return None
    if str(text) in STORAGE_GB:
        return float(STORAGE_GB[str(text)])
    total = 0.0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(tb|gb)", str(text).lower()):
        total += float(amount) * (1000 if unit == "tb" else 1)
    return total or None


def listify(v):
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def has_issue(issues, ignore=()):
    return int(any(i != "None" and i not in ignore for i in listify(issues)))


def any_in(issues, names):
    return int(any(i in names for i in listify(issues)))


def resolve_brand(category, subtype, brand):
    """Accept a brand id or name and return the display name used in training data."""
    if not known(brand):
        return None
    for b in catalog.list_brands(category, subtype):
        if str(brand).lower() in (b["id"], b["name"].lower()):
            return b["name"]
    return str(brand)


# ------------------------------------------------------- shared condition mapping
def condition_columns(condition, accessories, notes):
    year = condition.get("purchase_year")
    if str(year) == "Before 2012":
        age = MAX_TRAIN_AGE
        notes.append("Items from before 2012 are treated as 12 years old, the oldest age the model was trained on.")
    else:
        y = num(year)
        age = int(np.clip(CURRENT_YEAR - y, 0, MAX_TRAIN_AGE)) if y is not None else None
    warranty = condition.get("warranty_available")
    acc = [str(a) for a in listify(accessories)]
    return {
        "purchase_year": (CURRENT_YEAR - age) if age is not None else None,
        "age_years": age,
        "physical_condition": condition.get("physical_condition"),
        "working_status": condition.get("working_status"),
        "repair_history": condition.get("repair_history"),
        "warranty_available": warranty,
        "warranty_left": condition.get("warranty_left") if warranty == "Yes" else np.nan,
        "original_box": "Yes" if any(a in ("Original box", "Original packaging") for a in acc) else "No",
        "purchase_bill": "Yes" if any(a.startswith("Purchase bill") for a in acc) else "No",
        "original_charger": "Yes" if "Original charger" in acc else "No",
    }


# ----------------------------------------------------------- per-group row builders
def laptop_row(brand, specs, condition, notes):
    cpu = specs.get("cpu")
    tier = CPU_TIER.get(cpu) if known(cpu) else None
    if tier is None and known(cpu):
        tier = cpu_tier_from_text(cpu)
    gtype = specs.get("graphics_type")
    dedicated = gtype in ("dedicated", "both")
    dgpu = specs.get("dgpu_model") if dedicated else None
    return {
        "brand": brand, "cpu_tier": tier, "ram_capacity_gb": num(specs.get("ram_capacity_gb")),
        "storage_gb": storage_gb(specs.get("storage_capacity")), "graphics_type": gtype,
        "dgpu_tier": (DGPU_TIER.get(dgpu) if known(dgpu) else None) if dedicated else 0.0,
        "dgpu_vram_gb": num(specs.get("dgpu_vram_gb")) if dedicated else 0.0,
        "battery_health": specs.get("battery_health"),
        "display_damage": any_in(condition.get("issues"), ["Display damage"]),
        "battery_issue": any_in(condition.get("issues"), ["Battery issue"]),
        "keyboard_trackpad_issue": any_in(condition.get("issues"), ["Keyboard problem", "Trackpad problem"]),
        "charging_issue": any_in(condition.get("issues"), ["Charging problem"]),
        "other_hw_issue": any_in(condition.get("issues"), ["Body damage", "Motherboard issue", "Port problem", "Speaker problem",
                                                           "Microphone problem", "Wi-Fi problem", "Bluetooth problem", "Webcam problem"]),
    }


def desktop_row(subtype, brand, specs, condition, notes):
    dedicated = specs.get("gpu_present") == "Dedicated graphics card"
    storage = storage_gb(specs.get("storage_capacity") if subtype == "branded_pc" else specs.get("storage_summary"))
    gpu_name = specs.get("gpu_model") if dedicated else None
    gpu_t = (gpu_tier_from_text(gpu_name) if known(gpu_name) else None) if dedicated else 0.0
    if dedicated and known(gpu_name) and gpu_t is None:
        notes.append("The graphics card name was not recognised, so its performance level was treated as unknown.")
    cpu_t = cpu_tier_from_text(specs.get("cpu")) if known(specs.get("cpu")) else None
    if known(specs.get("cpu")) and cpu_t is None:
        notes.append("The processor name was not recognised, so its performance level was treated as unknown.")
    return {
        "desktop_type": subtype, "brand": "Custom build" if subtype == "custom_pc" else brand,
        "cpu_tier": cpu_t, "ram_capacity_gb": num(specs.get("ram_capacity_gb")), "storage_gb": storage,
        "has_dedicated_gpu": int(dedicated), "gpu_tier": gpu_t,
        "psu_wattage": (num(specs.get("psu_wattage")) if subtype == "custom_pc" else 0),
        "reported_issue": has_issue(condition.get("issues")),
    }


_RAM_TIER = {"DDR3": 1.0, "DDR4": 2.0, "DDR5": 3.0}
_SSD_TIER = {"SATA": 1.0, "NVMe PCIe 3.0": 2.0, "NVMe PCIe 4.0": 3.0}
_MB_TIER = {"AM3+": 1.0, "AM4": 2.0, "AM5": 3.5, "LGA1151": 2.0, "LGA1200": 2.0, "LGA1700": 3.0, "LGA1851": 3.5}
_PSU_EFF = {"Not rated": "80+ White", "80+ White": "80+ White", "80+ Bronze": "80+ Bronze", "80+ Silver": "80+ Bronze",
            "80+ Gold": "80+ Gold", "80+ Platinum": "80+ Gold", "80+ Titanium": "80+ Gold"}
_PSU_TIER = {"80+ White": 1.0, "80+ Bronze": 2.0, "80+ Gold": 3.0}
_COOLER = {"Air cooler": "Air cooler", "Case fan": "Air cooler", "Other": "Air cooler",
           "AIO liquid cooler (120/140 mm)": "AIO 240 mm", "AIO liquid cooler (240 mm)": "AIO 240 mm",
           "AIO liquid cooler (280/360 mm)": "AIO 360 mm"}
_COOLER_TIER = {"Air cooler": 1.0, "AIO 240 mm": 2.0, "AIO 360 mm": 3.0}
_CABINET = {"Mini-ITX": "Micro-ATX", "Micro-ATX": "Micro-ATX", "Mid tower": "Mid tower", "Full tower": "Full tower"}
_CABINET_TIER = {"Micro-ATX": 1.0, "Mid tower": 2.0, "Full tower": 3.0}


def component_row(subtype, brand, model_id, specs, condition, notes):
    rec = {"subtype": subtype, "brand": brand, "spec_tier": None, "capacity": 0.0, "generation": "", "variant": "",
           "reported_issue": has_issue(condition.get("issues"))}
    if subtype == "cpu":
        c = next((x for x in catalog.SEED["cpus"] if x["id"] == model_id), None)
        if c:
            rec.update(brand=c["brand"], spec_tier=CPU_ANCHOR[c["name"]][1], generation=c["socket"])
    elif subtype == "gpu":
        g = next((x for x in catalog.SEED["gpus"] if x["id"] == model_id), None)
        if g:
            rec.update(spec_tier=GPU_ANCHOR[g["chip"]][1], capacity=num(specs.get("vram_gb")),
                       generation=specs.get("vram_type") if known(specs.get("vram_type")) else "")
        mined = "Mined on heavily" in listify(condition.get("issues"))
        rec["variant"] = "heavily_mined" if mined else "normal_use"
        rec["reported_issue"] = has_issue(condition.get("issues"), ignore=("Mined on heavily",))
    elif subtype == "ram":
        ddr, cap, mods, form = specs.get("ddr_generation"), num(specs.get("capacity_gb")), num(specs.get("module_count")) or 1, specs.get("form_factor")
        rec.update(spec_tier=_RAM_TIER.get(ddr), capacity=(cap * mods) if cap else None, generation=ddr,
                   variant=f"{form}_{int(mods)}x{int(cap)}" if cap and known(form) else "")
    elif subtype == "ssd":
        iface = specs.get("interface")
        if iface == "NVMe PCIe 5.0":
            iface = "NVMe PCIe 4.0"
            notes.append("PCIe 5.0 SSDs are treated as PCIe 4.0, the fastest type the model was trained on.")
        rec.update(spec_tier=_SSD_TIER.get(iface), capacity=storage_gb(specs.get("capacity")), generation=iface)
    elif subtype == "hdd":
        rpm = num(specs.get("rpm"))
        rpm = None if rpm is None else (5400 if rpm <= 5900 else 7200)
        rec.update(spec_tier=None if rpm is None else (1.0 if rpm == 5400 else 1.3), capacity=storage_gb(specs.get("capacity")),
                   generation=f"{rpm}rpm" if rpm else "")
    elif subtype == "motherboard":
        sock = specs.get("socket")
        ff = specs.get("form_factor")
        rec.update(spec_tier=_MB_TIER.get(sock), generation=sock, variant="ATX" if ff == "E-ATX" else ff)
    elif subtype == "psu":
        w = num(specs.get("wattage"))
        if w and w > 850:
            notes.append("Power supplies above 850 W are treated as 850 W, the largest size the model was trained on.")
            w = 850.0
        eff = _PSU_EFF.get(specs.get("efficiency"))
        rec.update(spec_tier=_PSU_TIER.get(eff), capacity=w, generation=eff)
    elif subtype == "cooler":
        v = _COOLER.get(specs.get("cooler_type"))
        rec.update(spec_tier=_COOLER_TIER.get(v), variant=v)
    elif subtype == "cabinet":
        v = _CABINET.get(specs.get("size"))
        rec.update(spec_tier=_CABINET_TIER.get(v), variant=v)
    elif subtype == "expansion_card":
        rec.update(spec_tier=1.0, variant=specs.get("card_type"))
    return rec


def monitor_row(brand, specs, condition, notes):
    issues = listify(condition.get("issues"))
    modelled = {"Dead or stuck pixels", "Backlight bleed", "None"}
    if any(i not in modelled for i in issues):
        notes.append("Only dead pixels and backlight bleed are modelled individually; other monitor problems are not used.")
    return {
        "brand": brand, "size_in": num(specs.get("size_in")), "resolution": specs.get("resolution"),
        "refresh_rate_hz": num(specs.get("refresh_rate_hz")), "panel": specs.get("panel"),
        "curved": 1 if specs.get("curved") == "Yes" else 0,
        "dead_pixels": any_in(issues, ["Dead or stuck pixels"]), "backlight_bleed": any_in(issues, ["Backlight bleed"]),
    }


_TYPE_FIELD = {"keyboard": "keyboard_type", "mouse": "mouse_type", "charger": "connector_type", "cable": "cable_category",
               "headset": "connectivity", "webcam": "resolution", "external_storage": "drive_type", "hub_dock": "device_type"}
_TIER = {"Budget": 1, "Mid-range": 2, "Premium": 3}


def peripheral_row(subtype, brand, specs, condition, notes):
    field = _TYPE_FIELD.get(subtype)
    opt = specs.get(field) if field else "Standard"
    conn = str(specs.get("connectivity") or "")
    wireless = int(any(s in f"{opt} {conn}" for s in ("wireless", "Wireless", "Bluetooth")))
    return {
        "subtype": subtype, "brand": "Generic" if brand in (None, "Other") else brand, "type_option": opt,
        "tier": _TIER.get(specs.get("quality_tier")), "wireless": wireless,
        "capacity_gb": (storage_gb(specs.get("capacity")) or 0.0) if subtype == "external_storage" else 0.0,
        "reported_issue": has_issue(condition.get("issues")),
    }


# ------------------------------------------------------------------- merge model data
def fill_known_specs(category, subtype, model_id, specs):
    """Fill specs the exact model fixes (status 'known'), without overriding the user's own answers."""
    if not model_id:
        return dict(specs)
    ms = catalog.model_specs(category, subtype, model_id)
    out = dict(specs)
    if ms:
        for fid, f in ms["fields"].items():
            if f["status"] in ("known", "confirm") and "value" in f and not known(out.get(fid)):
                out[fid] = f["value"]
    return out


# ------------------------------------------------------------------------ predict
def build_raw(category, subtype, brand, model_id, specs, condition, accessories):
    group = group_for(category, subtype)
    notes = []
    brand_name = resolve_brand(category, subtype, brand)
    if group == "laptops":
        row = laptop_row(brand_name, specs, condition, notes)
    elif group == "desktops":
        row = desktop_row(subtype, brand_name, specs, condition, notes)
    elif group == "components":
        row = component_row(subtype, brand_name, model_id, specs, condition, notes)
    elif group == "monitors":
        row = monitor_row(brand_name, specs, condition, notes)
    else:
        row = peripheral_row(subtype, brand_name, specs, condition, notes)
    row.update({k: v for k, v in condition_columns(condition, accessories, notes).items()
                if group == "laptops" or k != "original_charger"})
    return group, row, notes


def _predict_rows(group, rows):
    b = bundle()[group]
    X = engineer_features(pd.DataFrame(rows))
    X = X.reindex(columns=b["feature_columns"])
    return b["model"].predict(X), b


def _round(x):
    step = 50 if x < 5000 else 100
    return int(round(x / step) * step)


# What-if scenarios used to explain the estimate. Each changes ONE raw input and is re-scored by the model.
def _scenarios(row):
    out = []
    age = row.get("age_years")
    if age is not None and age < MAX_TRAIN_AGE:
        out.append(("age", f"Age ({int(age)} yr{'s' if age != 1 else ''})", {"age_years": age + 1, "purchase_year": CURRENT_YEAR - age - 1},
                    "One more year of age would change the estimate by"))
    if row.get("physical_condition") not in (None, "Like new"):
        out.append(("physical", f"Physical condition ({row['physical_condition']})", {"physical_condition": "Like new"}, "vs. Like new"))
    if row.get("working_status") not in (None, "Fully working"):
        out.append(("working", f"Working status ({row['working_status']})", {"working_status": "Fully working"}, "vs. fully working"))
    issue_cols = [c for c in ("display_damage", "battery_issue", "keyboard_trackpad_issue", "charging_issue", "other_hw_issue",
                              "dead_pixels", "backlight_bleed", "reported_issue") if row.get(c)]
    if issue_cols:
        out.append(("issues", "Reported problems", {c: 0 for c in issue_cols}, "vs. no problems"))
    if row.get("variant") == "heavily_mined":
        out.append(("mined", "Heavy mining use", {"variant": "normal_use"}, "vs. normal use"))
    if row.get("battery_health") in ("60% to 80%", "Below 60%"):
        out.append(("battery", f"Battery health ({row['battery_health']})", {"battery_health": "Above 80%"}, "vs. above 80%"))
    if row.get("repair_history") == "Yes":
        out.append(("repair", "Previously repaired", {"repair_history": "No"}, "vs. never repaired"))
    if row.get("warranty_available") == "Yes":
        out.append(("warranty", "Warranty available", {"warranty_available": "No", "warranty_left": np.nan}, "vs. no warranty"))
    accessories = {"original_box": "Original box", "purchase_bill": "Purchase bill", "original_charger": "Original charger"}
    present = [c for c in accessories if row.get(c) == "Yes"]
    if present:
        out.append(("accessories", "Included " + ", ".join(accessories[c].lower() for c in present),
                    {c: "No" for c in present}, "vs. not included"))
    return out


def explain(group, row, base_price):
    scen = _scenarios(row)
    if not scen:
        return []
    alt_rows = []
    for _, _, change, _ in scen:
        r = dict(row)
        r.update(change)
        alt_rows.append(r)
    alt, _ = _predict_rows(group, alt_rows)
    factors = []
    for (key, label, _, ref), p_alt in zip(scen, alt):
        if key == "age":
            impact = float(p_alt - base_price)          # next year's price minus today's
            verb = "lower" if impact < 0 else "raise"
            factors.append({"factor": label, "impact_inr": _round(abs(impact)) * (1 if impact >= 0 else -1),
                            "text": f"One more year of age would {verb} the estimate by about ₹{_round(abs(impact)):,}.",
                            "kind": "age"})
            continue
        impact = float(base_price - p_alt)                # how much this factor adds (+) or removes (-) vs the reference
        if abs(impact) < max(0.02 * base_price, 100):
            continue
        verb = "adds about" if impact > 0 else "reduces the estimate by about"
        factors.append({"factor": label, "impact_inr": _round(abs(impact)) * (1 if impact > 0 else -1),
                        "text": f"{label} {verb} ₹{_round(abs(impact)):,} {ref}.", "kind": key})
    factors.sort(key=lambda f: -abs(f["impact_inr"]))
    return factors


UNKNOWN_LABELS = {"cpu_tier": "Processor", "ram_capacity_gb": "RAM", "storage_gb": "Storage capacity",
                  "dgpu_tier": "Dedicated GPU model", "dgpu_vram_gb": "GPU memory (VRAM)", "gpu_tier": "Graphics card",
                  "size_in": "Screen size", "resolution": "Resolution", "refresh_rate_hz": "Refresh rate", "panel": "Panel type",
                  "spec_tier": "Key specification (model/type)", "capacity": "Capacity", "generation": "Generation or type",
                  "tier": "Quality level", "psu_wattage": "Power supply wattage", "age_years": "Purchase year",
                  "graphics_type": "Graphics type", "battery_health": "Battery health"}


def estimate(category, subtype, brand, model_id, specs, condition, accessories):
    """Validate nothing here (the caller did); build the row, predict, add range and factors."""
    group, row, notes = build_raw(category, subtype, brand, model_id, specs, condition, accessories)
    if group is None or group not in bundle():
        raise UnsupportedProduct(f"No trained model is available for {category}/{subtype}.")
    pred, b = _predict_rows(group, [row])
    price = float(pred[0])
    lo_r, hi_r = b["range_ratio"]
    unknown = sorted({UNKNOWN_LABELS[k] for k, v in row.items()
                      if k in UNKNOWN_LABELS and (v is None or (isinstance(v, float) and np.isnan(v)))})
    result = {
        "estimate_inr": _round(price),
        "range_inr": {"low": _round(price * lo_r), "high": _round(price * hi_r)},
        "range_basis": ("Range covers the middle 80% of how far this model's estimates were from the actual price on "
                        "training data it had not seen."),
        "factors": explain(group, row, price),
        "unknown_inputs": unknown,
        "assumptions": notes,
        "model_info": {"group": group, "algorithm": b["model_name"].replace("_", " ").title()},
        "data_note": metrics()["data_note"],
        "disclaimer": DISCLAIMER,
    }
    return result, row
