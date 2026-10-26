"""Read-only access to the product/spec data and the form schemas.

Everything the website shows (categories, brands, models, which fields to ask,
which specs are already known) comes from the JSON files in data/. Adding a
brand, model or category means editing those files, not this code.

Spec retrieval follows three rules:
  known   - the exact model has ONE reliable value: pre-filled, never asked
  choose  - the model has several values, or the entry is an unverified seed:
            the user must pick or confirm (options supplied)
  ask     - nothing is known: the user fills it in or marks it Unknown
Nothing is ever invented, and unverified models are never auto-filled.
"""
import json
from pathlib import Path

from tiers import CPU_TIER

DATA = Path(__file__).parent / "data"


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


CATEGORIES = _load("categories.json")
LAPTOPS = _load("laptops.json")
GRAPHICS = _load("graphics.json")
SEED = _load("components_seed.json")
BRANDS = _load("brands.json")

_CATEGORY = {c["id"]: c for c in CATEGORIES["categories"]}
LAPTOP_BRANDS = {b["id"]: b for b in LAPTOPS["brands"]}
LAPTOP_MODELS = {m["id"]: (b, m) for b in LAPTOPS["brands"] for m in b["models"]}
IGPU = {g["name"]: g for g in GRAPHICS["integrated"]}
DGPU = {g["name"]: g for g in GRAPHICS["dedicated"]}


# ----------------------------------------------------------------- categories
def list_categories():
    out = []
    for c in CATEGORIES["categories"]:
        out.append({"id": c["id"], "name": c["name"], "icon": c["icon"], "description": c["description"],
                    "subtypes": [{"id": s["id"], "name": s["name"]} for s in c.get("subtypes", [])]})
    return out


def get_block(category_id, subtype_id=None):
    """Return the form definition for a category (or one of its subtypes), or None."""
    cat = _CATEGORY.get(category_id)
    if not cat:
        return None
    if "subtypes" in cat:
        for s in cat["subtypes"]:
            if s["id"] == subtype_id:
                return s
        return None
    return None if subtype_id else cat


def needs_subtype(category_id):
    cat = _CATEGORY.get(category_id)
    return bool(cat and "subtypes" in cat)


def _options(field):
    """Static option list for a field, or None when options are dynamic / free entry."""
    if "options" in field:
        return list(field["options"])
    ref = field.get("options_ref")
    if ref:
        return list(CATEGORIES["option_lists"][ref])
    return None


def resolve_schema(category_id, subtype_id=None):
    block = get_block(category_id, subtype_id)
    if block is None:
        return None
    fields = []
    for f in block["spec_fields"]:
        item = {k: v for k, v in f.items() if k not in ("options_ref", "options_source")}
        opts = _options(f)
        if opts is not None:
            item["options"] = opts
        src = f.get("options_source")
        if src == "data/graphics.json#integrated":
            item["options_endpoint"] = "/api/graphics/options"
        elif src == "data/graphics.json#dedicated":
            item["options"] = [g["name"] for g in GRAPHICS["dedicated"]]
        elif src == "data/graphics.json#dedicated.vram_gb":
            item["options_endpoint"] = "/api/graphics/vram"
        if category_id == "laptops" and f["id"] == "cpu":
            item["options"] = list(CPU_TIER)         # used only when no model entry exists
        fields.append(item)
    condition = []
    for b in block["condition_blocks"]:
        for f in CATEGORIES["condition_blocks"][b]:
            item = {k: v for k, v in f.items() if k != "options_ref"}
            opts = _options(f)
            if opts is not None:
                item["options"] = opts
            condition.append(item)
    for f in block.get("condition_questions", []):
        condition.append(dict(f))
    return {"category": category_id, "subtype": subtype_id, "name": block.get("name"), "flow": block["flow"],
            "model_source": block["model_source"], "spec_fields": fields, "condition_fields": condition,
            "accessories": block["accessories"]}


# --------------------------------------------------------------------- brands
def list_brands(category_id, subtype_id=None):
    if category_id == "laptops":
        return [{"id": b["id"], "name": b["name"], "model_count": len(b["models"])} for b in LAPTOPS["brands"]]
    if category_id == "components" and subtype_id == "cpu":
        return [{"id": n.lower(), "name": n} for n in ("Intel", "AMD")]
    if category_id == "components" and subtype_id == "gpu":
        return [{"id": b.lower(), "name": b} for b in SEED["gpu_board_brands"]]
    if category_id == "desktops" and subtype_id == "custom_pc":
        return []
    key = f"{category_id}/{subtype_id}" if f"{category_id}/{subtype_id}" in BRANDS else category_id
    names = BRANDS.get(key)
    return [{"id": n.lower(), "name": n} for n in names] if names else []


def list_models(category_id, subtype_id, brand_id):
    """Models for a brand. An empty list means 'no database entries: enter the model manually'."""
    if category_id == "laptops":
        b = LAPTOP_BRANDS.get(brand_id)
        if not b:
            return None
        return [{"id": m["id"], "name": m["name"], "series": m.get("series"), "verified": bool(m.get("verified"))}
                for m in b["models"]]
    if category_id == "components" and subtype_id == "cpu":
        return [{"id": c["id"], "name": c["name"]} for c in SEED["cpus"] if c["brand"].lower() == brand_id]
    if category_id == "components" and subtype_id == "gpu":
        return [{"id": g["id"], "name": g["chip"]} for g in SEED["gpus"]]
    return []


# ----------------------------------------------------------------- model specs
def _field(status, value=None, options=None, note=None):
    out = {"status": status}
    if value is not None:
        out["value"] = value
    if options is not None:
        out["options"] = options
    if note:
        out["note"] = note
    return out


def _laptop_specs(brand, m):
    verified = bool(m.get("verified"))
    fixed = m.get("fixed", {})
    fields = {}
    unconfirmed = set(m.get("unconfirmed", []))
    upgradable = set(m.get("upgradable", []))
    spec_ids = ["cpu", "ram_capacity_gb", "ram_type", "ram_speed_mts", "ram_layout", "storage_type",
                "storage_capacity", "graphics_type", "igpu_model", "dgpu_model", "dgpu_vram_gb"]
    if verified:
        variants = m["variants"]
        for fid in spec_ids:
            vals = []
            for v in variants:
                if fid in v and v[fid] not in vals:
                    vals.append(v[fid])
            if fid in unconfirmed or not vals:
                fields[fid] = _field("ask")
            elif len(vals) == 1:
                note = "Confirm if you changed this after purchase." if fid in upgradable else None
                fields[fid] = _field("confirm" if fid in upgradable else "known", vals[0], note=note)
            else:
                fields[fid] = _field("choose", options=vals)
        # a single verified variant tells us whether a dedicated GPU exists, so graphics_type is known
    else:
        o = m.get("variant_options", {})
        for fid in spec_ids:
            if fid in o:
                fields[fid] = _field("choose", options=o[fid], note="Unverified model entry: please confirm.")
            elif fid == "graphics_type":
                fields[fid] = _field("choose", options=["integrated", "dedicated", "both"],
                                     note="Unverified model entry: please confirm.")
            else:
                fields[fid] = _field("ask")
    # fixed display/battery facts are shown in the summary and never asked when present
    for fid in ("display_size_in", "resolution", "refresh_rate_hz", "panel", "touchscreen", "battery_wh"):
        if fid in fixed:
            fields[fid] = _field("known", fixed[fid] if fid != "touchscreen" else ("Yes" if fixed[fid] else "No"))
        elif fid != "battery_wh":
            fields[fid] = _field("ask")
    return {"model": {"id": m["id"], "name": m["name"], "brand": brand["name"], "series": m.get("series"),
                      "verified": verified, "source_note": m.get("source_note")},
            "fields": fields, "variants": m.get("variants") if verified else None}


def model_specs(category_id, subtype_id, model_id):
    if category_id == "laptops":
        hit = LAPTOP_MODELS.get(model_id)
        return _laptop_specs(*hit) if hit else None
    if category_id == "components" and subtype_id == "cpu":
        c = next((x for x in SEED["cpus"] if x["id"] == model_id), None)
        if not c:
            return None
        return {"model": {"id": c["id"], "name": c["name"], "brand": c["brand"], "verified": True},
                "fields": {"cores": _field("known", c["cores"]), "threads": _field("known", c["threads"]),
                           "socket": _field("known", c["socket"])}}
    if category_id == "components" and subtype_id == "gpu":
        g = next((x for x in SEED["gpus"] if x["id"] == model_id), None)
        if not g:
            return None

        def pick(vals):
            return _field("known", vals[0]) if len(vals) == 1 else _field("choose", options=vals)
        return {"model": {"id": g["id"], "name": g["chip"], "verified": True},
                "fields": {"vram_gb": pick(g["vram_gb"]), "vram_type": pick(g["vram_type"])}}
    return None


# -------------------------------------------------------------------- graphics
def graphics_options(cpu=None):
    """Integrated GPUs for a CPU. If the CPU is not listed, return that vendor's iGPUs and say so."""
    all_igpu = GRAPHICS["integrated"]
    matched = [g for g in all_igpu if cpu and cpu in g["cpu_match"]]
    if matched:
        chosen, exact = matched, True
    else:
        vendor = next((v for v in ("AMD", "Intel", "Apple") if cpu and v.lower() in cpu.lower()), None)
        chosen = [g for g in all_igpu if vendor and g["vendor"] == vendor] or all_igpu
        exact = False
    info = GRAPHICS["integrated_memory_info"]
    out = []
    for g in chosen:
        mem = info.get(g["vendor"], info["default"])
        out.append({"name": g["name"], "vendor": g["vendor"], "memory": mem})
    return {"cpu": cpu, "exact_match": exact, "options": out,
            "dedicated": [g["name"] for g in GRAPHICS["dedicated"]]}


def graphics_vram(dgpu):
    g = DGPU.get(dgpu)
    return None if not g else {"dgpu": dgpu, "vram_gb": g["vram_gb"]}


# ------------------------------------------------------------------ validation
def _visible(field, values):
    cond = field.get("show_if")
    if not cond:
        return True
    return str(values.get(cond["field"])) in [str(v) for v in cond["in"]]


def is_unknown(v):
    """True for an empty answer or the explicit 'unknown' marker.

    'Not sure' is deliberately NOT treated as unknown here: on some questions
    (battery health) it is a real, accepted option that the model understands.
    """
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "unknown"))


def validate(schema, specs, condition):
    """Return a list of human-readable problems with a prediction request."""
    errors = []
    for fields, values, label in ((schema["spec_fields"], specs, "specs"), (schema["condition_fields"], condition, "condition")):
        for f in fields:
            if f.get("type") == "info" or not _visible(f, values):
                continue
            v = values.get(f["id"])
            if is_unknown(v):
                if f.get("required") and not (f.get("allow_unknown") and isinstance(v, str)):
                    errors.append(f"{f.get('label', f['id'])} is required")
                continue
            opts = f.get("options")
            if opts is not None and f["type"] == "select" and str(v) not in [str(o) for o in opts]:
                errors.append(f"{f.get('label', f['id'])}: '{v}' is not a valid choice")
            if opts is not None and f["type"] == "multiselect":
                bad = [x for x in (v if isinstance(v, list) else [v]) if str(x) not in [str(o) for o in opts]]
                if bad:
                    errors.append(f"{f.get('label', f['id'])}: invalid choice(s) {bad}")
            if f["type"] == "number":
                try:
                    float(v)
                except (TypeError, ValueError):
                    errors.append(f"{f.get('label', f['id'])} must be a number")
    return errors
