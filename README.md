# ReValue AI

Used Computer Components and Laptop Valuation & Resale Price Prediction System.
A Flask + scikit-learn web app that estimates the resale value of used computer hardware in ₹ using a trained ML regression model.

**This is a price-prediction tool only.** There is no buying, selling, checkout, payment, pickup or messaging anywhere
in the app — verified by an automated test (`check_api.py`) that confirms no such route exists.

**Status: complete and tested end to end**, homepage through prediction, confirmed by a from-scratch rebuild (regenerate
data -> retrain -> retest) right before this note was written.

---

## Quick start

```bash
pip install -r requirements.txt
python generate_dataset.py   # builds dataset/*.csv (only needed once, or after editing data/*.json)
python train_model.py        # trains and saves model/resale_model.pkl (only needed once, or after regenerating data)
python app.py                # starts the website
```
Open `http://127.0.0.1:5050`.

To use a different port (e.g. if 5050 is also taken): `PORT=8000 python app.py`, then open `http://127.0.0.1:8000`.

A pre-trained model and pre-generated dataset are already included in this zip, so `python app.py` alone is enough to
try it immediately; the first two commands are only needed if you change the data and want to rebuild from scratch.

## Deploy online

The project includes a Render Blueprint in `render.yaml`. To get a public URL:

1. Push the complete `revalue-ai` folder to a GitHub repository. Keep `model/resale_model.pkl` and the `data/` folder
   in the repository; the deployed app needs them at runtime.
2. Sign in to Render, choose **New > Blueprint**, and connect that GitHub repository.
3. Render reads `render.yaml`, installs the dependencies, and publishes the app. Open the public URL shown on the
   service page; `/api/health` is used for its health check.

The free Render service may sleep after inactivity, so the first request after a quiet period can take longer to load.
The deployed app uses the included trained model and does not need a separate training step.

---

## Project structure

```
revalue-ai/
├── data/                  Product specification data (brands, models, graphics, categories/forms)
│   ├── categories.json        Every category's form fields, condition questions, accessories
│   ├── laptops.json           Laptop brands/models (verified vs. seed, see note below)
│   ├── graphics.json          Integrated GPUs (shared memory) and dedicated GPUs (VRAM)
│   ├── components_seed.json   CPU and GPU chip specs
│   └── brands.json            Brand lists for categories with no model database
├── dataset/                Resale-price training data (SYNTHETIC — see dataset/DATASET.md)
│   ├── *.csv                   laptops, desktops, components, monitors, peripherals
│   └── DATASET.md              What every column means, how prices were generated, limitations
├── model/                  Trained model (resale_model.pkl) and its metrics (metrics.json)
├── reports/                 actual_vs_predicted.png (held-out test set)
├── templates/index.html    The website (single page)
├── static/css/style.css    Styling
├── static/js/app.js        The dynamic wizard (talks to the API below)
├── tiers.py                 Shared CPU/GPU tier tables (used by both the dataset and the live app)
├── generate_dataset.py      Builds the synthetic dataset
├── preprocess.py             Feature engineering + train/test split (shared by training and the app)
├── train_model.py            Trains, compares and saves the models
├── catalog.py                 Reads data/*.json, resolves the dynamic forms, validates requests
├── valuation.py                Turns a filled form into a prediction, range and explanation
├── app.py                      Flask routes
└── check_*.py / check_ui.mjs   Automated tests (see Testing below)
```

---

## How it works

1. **Specification data** (`data/`) separately identifies brands, models and their known hardware, independent of price.
2. **Resale-price data** (`dataset/`) is a synthetic set of past "sales" with features and condition, used only to train
   the model. These two kinds of data are deliberately kept apart, per the project brief.
3. **Preprocessing** (`preprocess.py`) turns raw rows into model-ready features: ordinal condition scores, missing-value
   handling, one-hot encoding for categories, and a handful of engineered features (issue count, accessory count, age-squared).
4. **Training** (`train_model.py`) compares Linear Regression against a Random Forest per product group using 5-fold
   cross-validation on the training split only, picks the better one, and reports final scores once on a held-out test
   split that was never used for model selection.
5. **The website** (`templates/`, `static/`, `app.py`) is a dynamic, schema-driven wizard: every category has its own
   fields, defined once in `data/categories.json`, so no generic one-size-fits-all form is ever shown. Known specs for a
   confirmed model are pre-filled and locked; unverified or variable specs are asked.
6. **Prediction** (`valuation.py`) maps the completed form to the same columns the model was trained on and returns a
   price, a range, and a plain-language breakdown of what raised or lowered the estimate.

### The Integrated / Dedicated / Both graphics rule
Implemented exactly as specified: choosing **Integrated** shows the integrated GPU and its *shared system memory*
(never called VRAM); choosing **Dedicated** shows the dedicated GPU and its real VRAM; choosing **Both** shows all four
fields. This is enforced in the data (`data/graphics.json`), the schema (`data/categories.json`'s `show_if` rules), the
backend (`catalog.py`), and the frontend (`app.js`) — and tested in both `check_api.py` and `check_ui.mjs`.

---

## Model results

Five product groups, each with its own model, chosen between Linear Regression and Random Forest by 5-fold
cross-validation, then scored once on a held-out test split:

| Group | Selected model | Test MAE (₹) | Test RMSE (₹) | Test R2 |
|---|---|---|---|---|
| Laptops | Random Forest | 4,825 | 6,571 | 0.952 |
| Desktops | Linear Regression | 3,429 | 4,520 | 0.965 |
| Components | Linear Regression | 906 | 1,659 | 0.941 |
| Monitors | Linear Regression | 898 | 1,301 | 0.958 |
| Peripherals | Linear Regression | 217 | 356 | 0.923 |

**Read these scores carefully.** The training data is synthetic (see `dataset/DATASET.md`): prices were built as a
product of multiplicative depreciation factors, which is close to linear once you take logs — so Linear Regression
winning in 4 of 5 groups is an artifact of how the data was generated, not evidence that it beats Random Forest in
general. These scores prove the **pipeline** works end to end; they are not evidence of accuracy on real resale prices.
Replace the CSVs in `dataset/` with real completed-sale data (same column names) to get a meaningful accuracy measurement.

---

## API

| Route | Purpose |
|---|---|
| `GET /api/health` | model status |
| `GET /api/categories` | the 6 categories and their subtypes |
| `GET /api/schema?category=&subtype=` | the dynamic form definition for one product type |
| `GET /api/brands?category=&subtype=` | brand list |
| `GET /api/models?category=&subtype=&brand=` | models for a brand (empty list = manual entry) |
| `GET /api/model-specs?category=&subtype=&model_id=` | known / choose / ask status for every spec field |
| `GET /api/graphics/options?cpu=` | integrated GPU options for a CPU (shared memory, never VRAM) |
| `GET /api/graphics/vram?dgpu=` | VRAM options for a dedicated GPU |
| `POST /api/predict` | validates the request, estimates the price, returns range + explanation |

---

## Testing

Every layer has its own automated check, and all of them pass after a complete from-scratch rebuild:

| Test | Checks |
|---|---|
| `validate_data.py` | The category/field schemas are internally consistent (no dangling references, no duplicate or repeated fields) |
| `check_dataset.py` | Prices are positive, fall with age and worse condition, and carry no leakage columns |
| `check_preprocessing.py` | No train/test overlap, no target or ID leakage, fitting happens on train only, unseen categories don't crash it |
| `check_model.py` | Saved models give sane, cheaper-when-older/worse-condition predictions with a valid price range |
| `check_api.py` | All 25 product forms predict successfully end to end; the Integrated/Dedicated/Both logic; validation errors; **confirms no buy/sell/checkout/payment/pickup route exists anywhere** |
| `check_ui.mjs` | Drives the real page and real `app.js` in a headless browser (jsdom) against the live server — real clicks through a laptop valuation, a GPU valuation (with its subtype step), and back-navigation |

Run the Python checks any time with:
```bash
python validate_data.py && python check_dataset.py && python check_preprocessing.py && python check_model.py && python check_api.py
```
The UI test needs the server running and jsdom installed once: `npm install jsdom`, then with `python app.py` running
in one terminal, `node check_ui.mjs` in another.

---

## Known limitations

- **All resale prices are synthetic** (`dataset/DATASET.md` explains exactly how they were generated and why). Treat
  every accuracy figure as proof the system works, not as a real-world accuracy claim.
- **Only one laptop is spec-verified against real listings**: the HP Victus 15 fb3009AX. Every other laptop model is an
  unverified seed entry, so the form always asks the user to confirm its specs rather than silently trusting them.
- **Rare spec combinations** barely present in training (e.g. a high-tier CPU paired with integrated-only graphics on a
  model that always ships with a dedicated GPU in the data) can get an unreliable estimate, because the model is
  extrapolating outside what it has seen. The app does not currently detect or flag this case specifically.
- **Not built:** valuation history, an analytics/admin dashboard, and market-comparison listings — all explicitly
  optional in the original project brief.

## Compliance with the project's critical rules
No transaction features of any kind exist (checked by an automated test, not just by inspection); Cashkr was used only
as a general layout reference, not copied; all required categories are present and independently schema-driven; the
Integrated/Dedicated/Both logic is implemented exactly as specified; specifications are retrieved automatically where
reliable and otherwise asked from the user, never invented; the model is a real trained regression model with no
hardcoded prices; and the synthetic nature of the training data is disclosed in the UI (`data_note` on every prediction)
and in this document, not hidden.
