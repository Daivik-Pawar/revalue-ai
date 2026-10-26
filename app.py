"""ReValue AI: Flask backend.

A price-ESTIMATION service only. There are deliberately no buy, sell, checkout,
payment, pickup, shipping or messaging routes.

Run:  python app.py      then open http://127.0.0.1:5050
"""
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import catalog
import valuation

app = Flask(__name__)
app.json.sort_keys = False
ROOT = Path(__file__).parent


def err(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


# ------------------------------------------------------------------------ pages
@app.get("/")
def home():
    if (ROOT / "templates" / "index.html").exists():
        return render_template("index.html")
    return jsonify({"name": "ReValue AI", "status": "backend running", "note": "Web pages are added in the next build step.",
                    "api": ["/api/health", "/api/categories", "/api/schema", "/api/brands", "/api/models",
                            "/api/model-specs", "/api/graphics/options", "/api/graphics/vram", "POST /api/predict"]})


# -------------------------------------------------------------------------- API
@app.get("/api/health")
def health():
    try:
        groups = sorted(valuation.bundle())
    except Exception as e:                       # model file missing or unreadable
        return err(f"Model could not be loaded: {e}", 503)
    return jsonify({"status": "ok", "models_loaded": groups, "data_note": valuation.metrics()["data_note"]})


@app.get("/api/categories")
def categories():
    return jsonify({"categories": catalog.list_categories()})


def _cat_args():
    category = request.args.get("category", "")
    subtype = request.args.get("subtype") or None
    return category, subtype


@app.get("/api/schema")
def schema():
    category, subtype = _cat_args()
    if category and catalog.needs_subtype(category) and not subtype:
        subs = next(c["subtypes"] for c in catalog.list_categories() if c["id"] == category)
        return err(f"'{category}' needs a subtype.", 400, subtypes=[s["id"] for s in subs])
    s = catalog.resolve_schema(category, subtype)
    return jsonify(s) if s else err("Unknown category or subtype.", 404)


@app.get("/api/brands")
def brands():
    category, subtype = _cat_args()
    if catalog.get_block(category, subtype) is None:
        return err("Unknown category or subtype.", 404)
    return jsonify({"brands": catalog.list_brands(category, subtype)})


@app.get("/api/models")
def models():
    category, subtype = _cat_args()
    brand = (request.args.get("brand") or "").lower()
    if catalog.get_block(category, subtype) is None:
        return err("Unknown category or subtype.", 404)
    found = catalog.list_models(category, subtype, brand)
    if found is None:
        return err("Unknown brand.", 404)
    return jsonify({"models": found, "manual_entry": len(found) == 0})


@app.get("/api/model-specs")
def model_specs():
    category, subtype = _cat_args()
    model_id = request.args.get("model_id", "")
    ms = catalog.model_specs(category, subtype, model_id)
    return jsonify(ms) if ms else err("Unknown model.", 404)


@app.get("/api/graphics/options")
def graphics_options():
    return jsonify(catalog.graphics_options(request.args.get("cpu") or None))


@app.get("/api/graphics/vram")
def graphics_vram():
    g = catalog.graphics_vram(request.args.get("dgpu", ""))
    return jsonify(g) if g else err("Unknown dedicated GPU.", 404)


def _label_value_pairs(fields, values):
    out = []
    for f in fields:
        if f.get("type") == "info" or not catalog._visible(f, values):
            continue
        v = values.get(f["id"])
        if v is None or v == "" or v == []:
            continue
        if f.get("option_labels") and v in f["option_labels"]:
            v = f["option_labels"][v]
        out.append({"label": f.get("label", f["id"]), "value": ", ".join(map(str, v)) if isinstance(v, list) else v})
    return out


@app.post("/api/predict")
def predict():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return err("Send a JSON object.")
    category = body.get("category")
    subtype = body.get("subtype") or None
    brand, model_id = body.get("brand"), body.get("model_id")
    specs, condition = body.get("specs") or {}, body.get("condition") or {}
    accessories = body.get("accessories") or []
    if not all(isinstance(x, dict) for x in (specs, condition)) or not isinstance(accessories, list):
        return err("'specs' and 'condition' must be objects and 'accessories' a list.")

    schema_ = catalog.resolve_schema(category, subtype)
    if schema_ is None:
        return err("Unknown or incomplete category/subtype.", 404)

    problems = []
    # brand / model steps required by this product's flow
    brand_list = catalog.list_brands(category, subtype)
    if "brand" in schema_["flow"] and brand_list and valuation.resolve_brand(category, subtype, brand) is None:
        problems.append("Brand is required")
    if "model" in schema_["flow"] and brand:
        found = catalog.list_models(category, subtype, str(brand).lower())
        if found and not model_id:
            problems.append("Model is required")
        if model_id and found is not None and model_id not in [m["id"] for m in found]:
            problems.append("Model does not belong to the selected brand")
    specs = valuation.fill_known_specs(category, subtype, model_id, specs)
    problems += catalog.validate(schema_, specs, condition)
    if problems:
        return err("Some answers are missing or invalid.", 400, details=problems)

    try:
        result, _ = valuation.estimate(category, subtype, brand, model_id, specs, condition, accessories)
    except valuation.UnsupportedProduct as e:
        return err(str(e), 422)

    name = None
    if model_id:
        ms = catalog.model_specs(category, subtype, model_id)
        name = ms["model"]["name"] if ms else None
    if not name:
        name = " ".join(x for x in [valuation.resolve_brand(category, subtype, brand), specs.get("model_name"),
                                    schema_["name"] if not specs.get("model_name") else None] if x)
    result["product"] = {"category": category, "subtype": subtype, "type": schema_["name"], "brand": valuation.resolve_brand(category, subtype, brand),
                         "model_id": model_id, "name": name}
    result["confirmed_specs"] = _label_value_pairs(schema_["spec_fields"], specs)
    result["condition_summary"] = _label_value_pairs(schema_["condition_fields"], condition)
    if accessories:
        result["condition_summary"].append({"label": "Included items", "value": ", ".join(map(str, accessories))})
    return jsonify(result)


# ----------------------------------------------------------------- error pages
@app.errorhandler(404)
def not_found(_):
    return err("Not found.", 404)


@app.errorhandler(405)
def bad_method(_):
    return err("Method not allowed.", 405)


@app.errorhandler(500)
def server_error(_):
    return err("Something went wrong on the server.", 500)


if __name__ == "__main__":
    import os
    # Port 5000 is already taken on many machines (e.g. macOS AirPlay Receiver), so this now
    # defaults to 5050 instead. Override with:  PORT=8000 python app.py
    port = int(os.environ.get("PORT", 5050))
    print(f"ReValue AI running at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
