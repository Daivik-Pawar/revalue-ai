"""Sanity tests for the saved models. Run: python check_model.py"""
import sys
import joblib
import numpy as np
from preprocess import GROUPS, engineer_features, load_group

bundle = joblib.load("model/resale_model.pkl")
problems = []
def bad(m): problems.append(m)

def predict(group, raw):
    X = engineer_features(raw)[bundle[group]["feature_columns"]]
    return bundle[group]["model"].predict(X)

for g in GROUPS:
    if g not in bundle: bad(f"{g}: missing from bundle"); continue
    raw = load_group(g).sample(60, random_state=1).reset_index(drop=True)
    base = predict(g, raw)
    if not np.isfinite(base).all() or (base <= 0).any(): bad(f"{g}: non-finite or non-positive predictions")
    lo, hi = bundle[g]["range_ratio"]
    if not (0 < lo < 1 < hi): bad(f"{g}: price range ratio {lo:.2f}-{hi:.2f} does not bracket 1")
    older = raw.copy(); older["age_years"] = older["age_years"] + 4; older["purchase_year"] = older["purchase_year"] - 4
    if predict(g, older).mean() >= base.mean(): bad(f"{g}: older items are not predicted cheaper")
    worn = raw.copy(); worn["physical_condition"] = "Poor (heavy wear)"; worn["working_status"] = "Not working"
    if predict(g, worn).mean() >= base.mean(): bad(f"{g}: worse condition is not predicted cheaper")
    print(f"{g:12s} model={bundle[g]['model_name']:18s} mean pred ₹{base.mean():>8,.0f} | +4 years ₹{predict(g, older).mean():>8,.0f} | poor+not working ₹{predict(g, worn).mean():>8,.0f}")

if problems:
    print("\nFAILED:"); [print(" -", p) for p in problems]; sys.exit(1)
print("\nOK: model sanity checks passed")
