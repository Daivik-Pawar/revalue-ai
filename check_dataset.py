"""Sanity checks for the synthetic datasets. Run: python check_dataset.py"""
import sys
from pathlib import Path
import pandas as pd

D = Path(__file__).parent / "dataset"
FILES = ["laptops", "desktops", "components", "monitors", "peripherals"]
problems = []
def bad(msg): problems.append(msg)

for name in FILES:
    df = pd.read_csv(D / f"{name}.csv")
    t = df["resale_price_inr"]
    if t.isna().any(): bad(f"{name}: missing target values")
    if (t <= 0).any(): bad(f"{name}: non-positive prices")
    if df["row_id"].duplicated().any(): bad(f"{name}: duplicate row_id")
    if set(df["price_type"]) != {"completed_sale", "asking"}: bad(f"{name}: price_type values wrong")
    if set(df["data_source"]) != {"synthetic_v1"}: bad(f"{name}: data_source must be synthetic_v1")
    leak = [c for c in df.columns if "new_price" in c.lower() or "msrp" in c.lower() or "launch" in c.lower()]
    if leak: bad(f"{name}: possible leakage columns {leak}")
    comp = df[df.price_type == "completed_sale"]
    # age should lower price, condition should lower price (monotonic on medians)
    if comp[["age_years", "resale_price_inr"]].corr(method="spearman").iloc[0, 1] >= -0.15:
        bad(f"{name}: price does not fall with age")
    med = comp.groupby("physical_condition")["resale_price_inr"].median()
    order = ["Like new", "Good (light wear)", "Fair (visible wear)", "Poor (heavy wear)"]
    if not all(med[order[i]] > med[order[i + 1]] for i in range(3)): bad(f"{name}: condition medians not ordered {med.to_dict()}")
    w = comp.groupby("working_status")["resale_price_inr"].median()
    if not (w["Fully working"] > w["Works with minor issues"] > w["Not working"]): bad(f"{name}: working-status medians not ordered")
    ask = df[df.price_type == "asking"]
    print(f"{name:12s} rows={len(df):5d} completed={len(comp):5d} asking={len(ask):4d} "
          f"price range={t.min():,.0f}..{t.max():,.0f}  dup rows (excl id)={df.drop(columns='row_id').duplicated().sum()}")

lap = pd.read_csv(D / "laptops.csv")
lc = lap[lap.price_type == "completed_sale"]
if lc[lc.graphics_type == "integrated"]["dgpu_vram_gb"].ne(0).any(): bad("laptops: integrated-only row has dedicated VRAM")
if lc[lc.graphics_type != "integrated"]["dgpu_model"].eq("None").any(): bad("laptops: dedicated row without GPU model")
print("laptop mean price by brand:\n", lc.groupby("brand")["resale_price_inr"].mean().round(0).to_string())

if problems:
    print("\nFAILED:"); [print(" -", p) for p in problems]; sys.exit(1)
print("\nOK: all dataset checks passed")
