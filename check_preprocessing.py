"""Tests for preprocess.py. Run: python check_preprocessing.py"""
import sys
import numpy as np
import pandas as pd
from preprocess import GROUPS, TARGET, NON_FEATURES, load_group, engineer_features, make_preprocessor, split_group

problems = []
def bad(m): problems.append(m)

for g in GROUPS:
    raw = load_group(g)
    if (raw["price_type"] != "completed_sale").any(): bad(f"{g}: asking rows not removed")
    Xtr, Xte, ytr, yte = split_group(g)
    # 1. split sizes and no overlap
    if abs(len(Xte) / (len(Xtr) + len(Xte)) - 0.20) > 0.01: bad(f"{g}: test share not ~20%")
    if set(Xtr.index) & set(Xte.index): bad(f"{g}: train and test rows overlap")
    # 2. target and bookkeeping never inside the features
    forbidden = set(NON_FEATURES + [TARGET]) & set(Xtr.columns)
    if forbidden: bad(f"{g}: forbidden columns in features {forbidden}")
    # 3. fit on TRAIN only, transform both
    pre = make_preprocessor(Xtr)
    A = pre.fit_transform(Xtr)
    B = pre.transform(Xte)
    A = A.toarray() if hasattr(A, "toarray") else A
    B = B.toarray() if hasattr(B, "toarray") else B
    if np.isnan(A).any() or np.isnan(B).any(): bad(f"{g}: NaN left after preprocessing")
    if A.shape[1] != B.shape[1]: bad(f"{g}: train/test feature counts differ")
    # 4. scaler learned from train only: train numeric means ~0, test means need not be
    n_num = len(pre.transformers_[0][2])
    if n_num and abs(A[:, :n_num].mean(axis=0)).max() > 1e-6: bad(f"{g}: train numeric columns not centred")
    # 5. unseen category and unknown answers must not crash
    row = Xte.iloc[[0]].copy()
    for c in row.select_dtypes(exclude="number").columns:
        row[c] = "BrandNeverSeenBefore"
    for c in row.select_dtypes(include="number").columns[:3]:
        row[c] = np.nan
    try:
        pre.transform(row)
    except Exception as e:
        bad(f"{g}: crashes on unseen category / missing values: {e}")
    print(f"{g:12s} completed rows={len(raw):5d}  train={len(Xtr):5d} test={len(Xte):4d}  "
          f"raw cols={raw.shape[1]:2d} -> features={Xtr.shape[1]:2d} -> encoded={A.shape[1]:3d}")

# Targeted feature-engineering tests on laptops
raw = pd.DataFrame([{
    "brand": "Apple", "age_years": 3, "physical_condition": "Good (light wear)", "working_status": "Fully working",
    "battery_health": "Not sure", "repair_history": "No", "warranty_available": "No", "warranty_left": np.nan,
    "original_box": "Yes", "purchase_bill": "No", "original_charger": "Yes", "graphics_type": "integrated",
    "display_damage": 1, "battery_issue": 0, "ram_capacity_gb": 8, "storage_gb": 256, "purchase_year": 2023,
    "model_id": "x", "row_id": 1, "price_type": "completed_sale", "data_source": "synthetic_v1"}])
f = engineer_features(raw).iloc[0]
checks = {
    "physical score": f["physical_condition_score"] == 2,
    "battery 'Not sure' -> NaN + flag": np.isnan(f["battery_health_score"]) and f["battery_health_unknown"] == 1,
    "no warranty -> 0 months": f["warranty_months"] == 0,
    "issue_count": f["issue_count"] == 1,
    "accessory_count": f["accessory_count"] == 2,
    "is_apple": f["is_apple"] == 1,
    "no dedicated gpu": f["has_dedicated_gpu"] == 0,
    "age squared": f["age_years_sq"] == 9,
}
for name, ok in checks.items():
    if not ok: bad(f"feature test failed: {name}")
if "purchase_year" in engineer_features(raw).columns or "model_id" in engineer_features(raw).columns:
    bad("identifier columns not dropped")

if problems:
    print("\nFAILED:"); [print(" -", p) for p in problems]; sys.exit(1)
print(f"\nOK: preprocessing checks passed ({len(checks)} feature tests + {len(GROUPS)} group tests)")
