# Dataset documentation (synthetic_v1)

**All prices in these files are SYNTHETIC.** They were produced by `generate_dataset.py` from depreciation rules
plus random noise. They are not real market sales. Any accuracy metric measured on them shows the pipeline works;
it does not show how accurate the model would be on real used-product prices.

## Files
| File | Rows | Used for |
|---|---|---|
| laptops.csv | 1500 | Laptop model (spec-driven, follows data/laptops.json) |
| desktops.csv | 400 | Branded and custom desktops |
| components.csv | 1400 | CPU, GPU, RAM, SSD, HDD, motherboard, PSU, cooler, cabinet, expansion card |
| monitors.csv | 450 | Monitors |
| peripherals.csv | 600 | Keyboards, mice, chargers, cables, headsets, webcams, external storage, hubs/docks, cooling pads |

## Common columns
- `row_id`: row number. Not a feature.
- `resale_price_inr`: **target** (₹).
- `price_type`: `completed_sale` or `asking`. About 15% of rows are asking prices (completed price inflated by 8-25%).
  **Train on `completed_sale` rows only**; asking prices are kept to show the difference.
- `data_source`: always `synthetic_v1`. Not a feature.
- Age and condition: `purchase_year`, `age_years` (derived from purchase year, 2026 baseline), `physical_condition`,
  `working_status`, `repair_history`, `warranty_available`, `warranty_left` (empty when no warranty),
  `original_box`, `purchase_bill`.
- Laptop-only: `original_charger`, `battery_health`, issue flags (`display_damage`, `battery_issue`,
  `keyboard_trackpad_issue`, `charging_issue`, `other_hw_issue`). Monitors have `dead_pixels` and `backlight_bleed`.
- `reported_issue` (desktops, components, peripherals): 1 when the item has a reported fault, as the user would tick in the form.
- Specification columns differ per file; tiers (`cpu_tier`, `dgpu_tier`, `gpu_tier`, `spec_tier`) are
  self-defined 1-5 orderings of parts, not benchmark scores.
- `purchase_year` and `age_years` carry the same information; use one of them in the model.
- `model_id` (laptops) and `model_name` (components) are high-cardinality identifiers; the preprocessing step decides how to treat them.

## How prices were generated
1. A hidden "new price" is built from the specs using illustrative rupee formulas. It is NOT saved in the CSVs
   (saving it would leak the answer).
2. It is multiplied by an age-retention curve, then by condition, working status, repair history, warranty,
   accessory, battery and fault factors.
3. Log-normal noise (about 6%) is added and the result is rounded to the nearest ₹50.
Older items are made more likely to be worn, repaired or faulty, as in reality.

## Known limitations
- Synthetic relationships are simple and clean, so scores will look better than real data would allow.
- Some spec combinations are rare or absent in training (e.g. a high-end CPU with integrated-only graphics on a model
  that always ships with a dedicated GPU). The trained models can extrapolate unreliably for such combinations; the
  app does not detect or flag this, so treat estimates for unusual configurations with extra caution.
- New-price anchors are illustrative approximations, not real launch prices.
- Brands/models without seed data in `data/` are not represented.
- Laptop rows for unverified models use option lists, so some combinations may not exist as real products.

## Replacing it with real data
Put a real CSV with the same column names in `dataset/` (completed sales preferred) and rerun training.
