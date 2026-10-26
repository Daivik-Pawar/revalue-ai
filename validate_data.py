"""Validate the product-spec data and category schemas.

Run:  python validate_data.py
Exits with code 1 and prints every problem found if any rule is broken.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
VALID_FLOW = {"brand", "model", "components", "specs", "condition", "accessories"}
VALID_ASK = {"always", "confirm_if_varies", "only_if_missing"}
VALID_TYPES = {"select", "multiselect", "number", "text", "info"}
VALID_MODEL_SOURCE_PREFIXES = ("manual", "none", "data/")

errors = []


def err(msg):
    errors.append(msg)


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def check_fields(fields, where, option_lists):
    ids = [f["id"] for f in fields]
    if len(ids) != len(set(ids)):
        err(f"{where}: duplicate field ids")
    for f in fields:
        loc = f"{where}.{f['id']}"
        if f.get("type") not in VALID_TYPES:
            err(f"{loc}: bad type {f.get('type')!r}")
        if "ask" in f and f["ask"] not in VALID_ASK:
            err(f"{loc}: bad ask {f['ask']!r}")
        ref = f.get("options_ref")
        if ref and ref not in option_lists:
            err(f"{loc}: options_ref {ref!r} not defined")
        cond = f.get("show_if")
        if cond:
            if cond["field"] not in ids:
                err(f"{loc}: show_if references unknown field {cond['field']!r}")
            else:
                parent = next(x for x in fields if x["id"] == cond["field"])
                allowed = parent.get("options") or option_lists.get(parent.get("options_ref"), [])
                for v in cond["in"]:
                    if allowed and v not in allowed:
                        err(f"{loc}: show_if value {v!r} is not an option of {cond['field']!r}")


def check_spec_block(block, where, cat_data):
    flow = block.get("flow")
    if flow is None:
        err(f"{where}: missing flow")
    else:
        for step in flow:
            if step not in VALID_FLOW:
                err(f"{where}: unknown flow step {step!r}")
    ms = block.get("model_source")
    if not ms or not ms.startswith(VALID_MODEL_SOURCE_PREFIXES):
        err(f"{where}: bad model_source {ms!r}")
    if ms and ms.startswith("data/") and not (DATA.parent / ms.split("#")[0]).exists():
        err(f"{where}: model_source file missing: {ms}")
    check_fields(block["spec_fields"], f"{where}.spec_fields", cat_data["option_lists"])
    for b in block["condition_blocks"]:
        if b not in cat_data["condition_blocks"]:
            err(f"{where}: unknown condition block {b!r}")
    check_fields(block.get("condition_questions", []), f"{where}.condition_questions", cat_data["option_lists"])
    if "accessories" not in block:
        err(f"{where}: missing accessories list")
    # No question may be asked twice across spec fields and condition questions.
    spec_ids = {f["id"] for f in block["spec_fields"]}
    cond_ids = {f["id"] for b in block["condition_blocks"] for f in cat_data["condition_blocks"][b]}
    cond_ids |= {f["id"] for f in block.get("condition_questions", [])}
    dup = spec_ids & cond_ids
    if dup:
        err(f"{where}: field ids repeated between specs and condition: {sorted(dup)}")


def check_categories():
    cat = load("categories.json")
    ids = []
    for c in cat["categories"]:
        ids.append(c["id"])
        blocks = c.get("subtypes") or [c]
        sub_ids = [b["id"] for b in blocks]
        if len(sub_ids) != len(set(sub_ids)):
            err(f"{c['id']}: duplicate subtype ids")
        for b in blocks:
            check_spec_block(b, f"{c['id']}/{b['id']}", cat)
    if len(ids) != len(set(ids)):
        err("categories: duplicate category ids")
    required = {"laptops", "desktops", "components", "monitors", "keyboards_mice", "accessories"}
    missing = required - set(ids)
    if missing:
        err(f"categories: required categories missing: {sorted(missing)}")
    return cat


def check_laptops(cat):
    gfx = load("graphics.json")
    laptops = load("laptops.json")
    igpu = {g["name"]: g for g in gfx["integrated"]}
    dgpu = {g["name"]: g for g in gfx["dedicated"]}
    seen = set()
    for brand in laptops["brands"]:
        for m in brand["models"]:
            where = f"laptop {m['id']}"
            if m["id"] in seen:
                err(f"{where}: duplicate id")
            seen.add(m["id"])
            if m.get("verified"):
                if not m.get("variants"):
                    err(f"{where}: verified model needs explicit variants")
            else:
                if m.get("variants"):
                    err(f"{where}: unverified seed must use variant_options, not complete variants")
                if not m.get("variant_options"):
                    err(f"{where}: needs variant_options or variants")
            for v in m.get("variants", []):
                gt = v.get("graphics_type")
                if gt not in {"integrated", "dedicated", "both"}:
                    err(f"{where}: bad graphics_type {gt!r}")
                if gt in {"integrated", "both"}:
                    g = igpu.get(v.get("igpu_model"))
                    if not g:
                        err(f"{where}: unknown igpu {v.get('igpu_model')!r}")
                    elif v["cpu"] not in g["cpu_match"]:
                        err(f"{where}: iGPU {g['name']} is not listed for CPU {v['cpu']}")
                if gt in {"dedicated", "both"}:
                    d = dgpu.get(v.get("dgpu_model"))
                    if not d:
                        err(f"{where}: unknown dgpu {v.get('dgpu_model')!r}")
                    elif v.get("dgpu_vram_gb") not in d["vram_gb"]:
                        err(f"{where}: VRAM {v.get('dgpu_vram_gb')} invalid for {d['name']}")
                if gt == "integrated" and ("dgpu_model" in v or "dgpu_vram_gb" in v):
                    err(f"{where}: integrated-only variant lists a dedicated GPU")
            for name in m.get("variant_options", {}).get("dgpu_model", []):
                if name not in dgpu:
                    err(f"{where}: variant_options dgpu {name!r} not in graphics.json")
    # every iGPU memory vendor has info
    for g in gfx["integrated"]:
        if g["vendor"] not in gfx["integrated_memory_info"] and "default" not in gfx["integrated_memory_info"]:
            err(f"graphics: no memory info for {g['vendor']}")
    return len(seen)


def check_components():
    comp = load("components_seed.json")
    for key in ("cpus", "gpus"):
        ids = [x["id"] for x in comp[key]]
        if len(ids) != len(set(ids)):
            err(f"components_seed.{key}: duplicate ids")


if __name__ == "__main__":
    cat = check_categories()
    n_models = check_laptops(cat)
    check_components()
    n_blocks = sum(len(c.get("subtypes") or [1]) for c in cat["categories"])
    if errors:
        print(f"FAILED with {len(errors)} problem(s):")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"OK: {len(cat['categories'])} categories, {n_blocks} form definitions, {n_models} laptop models validated.")
