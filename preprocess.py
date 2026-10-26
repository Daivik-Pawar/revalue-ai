"""Preprocessing and feature engineering for ReValue AI.

The same functions are used for training (train_model.py) and for the Flask
app, so a user's form answers are converted to features exactly the way the
training rows were. Nothing here looks at the target, and every fitted step
(imputing, scaling, encoding) lives in a scikit-learn Pipeline that is fitted
on the TRAINING split only, which prevents leakage from the test set.

Public API:
    GROUPS                      dataset groups and their CSV files
    load_group(group)           raw completed-sale rows for one group
    engineer_features(df)       raw form-like rows -> model features (no target)
    make_preprocessor(X)        unfitted ColumnTransformer for a feature table
    split_group(group)          X_train, X_test, y_train, y_test
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATASET_DIR = Path(__file__).parent / "dataset"
GROUPS = {name: DATASET_DIR / f"{name}.csv" for name in
          ["laptops", "desktops", "components", "monitors", "peripherals"]}
TARGET = "resale_price_inr"
TEST_SIZE = 0.20
RANDOM_STATE = 42

# Columns that are identifiers / metadata, or duplicate other information.
#  - row_id, data_source, price_type: bookkeeping, not product facts
#  - purchase_year: same information as age_years (we keep age_years)
#  - model_id, model_name, cpu, dgpu_model: free-text identifiers; their
#    price-relevant content is already carried by tier / capacity columns
NON_FEATURES = ["row_id", "data_source", "price_type", "purchase_year",
                "model_id", "model_name", "cpu", "dgpu_model"]

# Ordered (ordinal) answers: a worse answer gets a lower number.
PHYSICAL_ORDER = {"Like new": 3, "Good (light wear)": 2, "Fair (visible wear)": 1, "Poor (heavy wear)": 0}
WORKING_ORDER = {"Fully working": 2, "Works with minor issues": 1, "Not working": 0}
BATTERY_ORDER = {"Above 80%": 2, "60% to 80%": 1, "Below 60%": 0}      # "Not sure" -> missing
WARRANTY_MONTHS = {"Under 3 months": 2, "3 to 6 months": 5, "6 to 12 months": 9, "More than 12 months": 15}
YES_NO = {"Yes": 1, "No": 0}
ISSUE_FLAGS = ["display_damage", "battery_issue", "keyboard_trackpad_issue", "charging_issue",
               "other_hw_issue", "dead_pixels", "backlight_bleed", "reported_issue"]


def load_group(group: str) -> pd.DataFrame:
    """Load one dataset and keep only completed-sale rows.

    Asking prices are dropped: they are what sellers hope to get, not what an
    item sold for, so using them would bias the model upward.
    """
    if group not in GROUPS:
        raise ValueError(f"Unknown group {group!r}. Choose from {list(GROUPS)}")
    df = pd.read_csv(GROUPS[group])
    df = df[df["price_type"] == "completed_sale"].copy()
    df = df.dropna(subset=[TARGET])
    df = df[df[TARGET] > 0]
    return df.reset_index(drop=True)


def engineer_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn raw form-like rows into model features. Never touches the target.

    Works on a DataFrame with the same raw columns as the CSVs (the Flask app
    builds such a frame from the user's answers). Columns a group does not have
    are simply skipped, and unknown answers become NaN so the imputer in the
    pipeline can fill them.
    """
    df = raw.copy()

    def has(c):
        return c in df.columns

    # ----- ordinal condition answers -> numbers (unknown / unseen -> NaN)
    if has("physical_condition"):
        df["physical_condition_score"] = df["physical_condition"].map(PHYSICAL_ORDER)
    if has("working_status"):
        df["working_status_score"] = df["working_status"].map(WORKING_ORDER)
    if has("battery_health"):
        df["battery_health_score"] = df["battery_health"].map(BATTERY_ORDER)   # "Not sure" -> NaN
        df["battery_health_unknown"] = (~df["battery_health"].isin(BATTERY_ORDER)).astype(int)

    # ----- yes/no answers -> 0/1
    for c in ["repair_history", "warranty_available", "original_box", "purchase_bill", "original_charger"]:
        if has(c):
            df[c] = df[c].map(YES_NO)

    # ----- warranty: remaining months (0 when there is no warranty)
    if has("warranty_left"):
        months = df["warranty_left"].map(WARRANTY_MONTHS)
        no_warranty = df["warranty_available"] == 0 if has("warranty_available") else months.isna()
        df["warranty_months"] = months.where(~no_warranty, 0)
        df = df.drop(columns=["warranty_left"])

    # ----- aggregates built only from other input columns
    issue_cols = [c for c in ISSUE_FLAGS if has(c)]
    if issue_cols:
        df["issue_count"] = df[issue_cols].fillna(0).sum(axis=1)
    acc_cols = [c for c in ["original_box", "purchase_bill", "original_charger"] if has(c)]
    if acc_cols:
        df["accessory_count"] = df[acc_cols].fillna(0).sum(axis=1)

    # ----- laptop specific
    if has("graphics_type"):
        df["has_dedicated_gpu"] = df["graphics_type"].isin(["dedicated", "both"]).astype(int)
    if has("brand"):
        df["is_apple"] = (df["brand"] == "Apple").astype(int)
    if has("ram_capacity_gb") and has("storage_gb"):
        df["ram_x_storage_log"] = np.log1p(df["ram_capacity_gb"]) + np.log1p(df["storage_gb"])
    if has("age_years"):
        df["age_years_sq"] = df["age_years"] ** 2   # depreciation is not linear in age

    # ----- drop columns that are identifiers, duplicates, or the target
    df = df.drop(columns=[c for c in NON_FEATURES + [TARGET] if c in df.columns])
    # raw ordinal text columns are replaced by their numeric scores above
    df = df.drop(columns=[c for c in ["physical_condition", "working_status", "battery_health"] if c in df.columns])
    return df


def make_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """Unfitted transformer for a feature table.

    Numeric columns: median imputation, then standard scaling (needed by
    Linear Regression, harmless for Random Forest).
    Categorical columns: most-frequent imputation, then one-hot encoding that
    ignores categories never seen in training (so a new brand cannot crash
    the app).
    """
    numeric = X.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in X.columns if c not in numeric]
    numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=False)),
                             ("scale", StandardScaler())])
    categorical_pipe = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                                 ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer([("num", numeric_pipe, numeric), ("cat", categorical_pipe, categorical)])


def split_group(group: str, test_size: float = TEST_SIZE, random_state: int = RANDOM_STATE):
    """Return X_train, X_test, y_train, y_test for one dataset group.

    The split is made BEFORE any fitting. The components group is stratified by
    subtype so every part type appears in both halves.
    """
    df = load_group(group)
    y = df[TARGET]
    X = engineer_features(df)
    strat = df["subtype"] if group in ("components", "peripherals") else None
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=strat)
