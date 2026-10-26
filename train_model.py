"""Train, compare and save the resale-price models.

For every dataset group (laptops, desktops, components, monitors, peripherals):
  1. Split 80/20 (fixed seed), see preprocess.split_group.
  2. Compare Linear Regression (baseline) and Random Forest Regressor using
     5-fold cross-validation on the TRAINING rows only.
  3. Pick the model with the lower cross-validated RMSE (selection never looks
     at the test set).
  4. Refit the chosen model on the full training split, then score it ONCE on
     the held-out test split (MAE, RMSE, R2). Both models' test scores are
     reported for the write-up, but only the CV result chose the winner.
  5. Estimate a price range from out-of-fold relative errors on training data.
  6. Save everything to model/resale_model.pkl and model/metrics.json.

Prices are right-skewed and depreciation is multiplicative, so both models
predict log(1 + price) and the result is converted back to rupees.

NOTE: the data is synthetic (see dataset/DATASET.md). These scores prove the
pipeline works; they are NOT evidence of accuracy on real market prices.

Run:  python train_model.py
"""
import json
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline

from preprocess import GROUPS, RANDOM_STATE, engineer_features, load_group, make_preprocessor, split_group

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MODEL_DIR = Path(__file__).parent / "model"
REPORT_DIR = Path(__file__).parent / "reports"
CV = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)


def build_pipeline(kind: str, X_train: pd.DataFrame):
    if kind == "linear_regression":
        est = LinearRegression()
    elif kind == "random_forest":
        est = RandomForestRegressor(n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=RANDOM_STATE)
    else:
        raise ValueError(kind)
    pipe = Pipeline([("prep", make_preprocessor(X_train)), ("model", est)])
    return TransformedTargetRegressor(regressor=pipe, func=np.log1p, inverse_func=np.expm1)


def scores(y_true, y_pred):
    return {"MAE": float(mean_absolute_error(y_true, y_pred)),
            "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "R2": float(r2_score(y_true, y_pred))}


def feature_importance(fitted, top=8):
    """Random Forest importances mapped back to readable feature names."""
    pipe = fitted.regressor_
    names = pipe.named_steps["prep"].get_feature_names_out()
    imp = pipe.named_steps["model"].feature_importances_
    # merge one-hot columns back to their source feature
    merged = {}
    for n, v in zip(names, imp):
        base = n.split("__", 1)[1]
        for prefix in sorted(pipe.named_steps["prep"].transformers_[1][2], key=len, reverse=True):
            if base.startswith(prefix + "_"):
                base = prefix
                break
        merged[base] = merged.get(base, 0.0) + float(v)
    return dict(sorted(merged.items(), key=lambda kv: -kv[1])[:top])


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    bundle, metrics, plots = {}, {}, {}
    for group in GROUPS:
        X_train, X_test, y_train, y_test = split_group(group)
        cv_res, test_res, fitted = {}, {}, {}
        for kind in ["linear_regression", "random_forest"]:
            oof = cross_val_predict(build_pipeline(kind, X_train), X_train, y_train, cv=CV)
            cv_res[kind] = scores(y_train, oof)
            fitted[kind] = build_pipeline(kind, X_train).fit(X_train, y_train)
            test_res[kind] = scores(y_test, fitted[kind].predict(X_test))
        winner = min(cv_res, key=lambda k: cv_res[k]["RMSE"])      # chosen on CV only
        # price range: 10th and 90th percentile of actual/predicted from out-of-fold training predictions
        oof_w = cross_val_predict(build_pipeline(winner, X_train), X_train, y_train, cv=CV)
        ratio = (y_train / np.maximum(oof_w, 1)).to_numpy()
        lo, hi = np.quantile(ratio, [0.10, 0.90])
        metrics[group] = {
            "rows_train": int(len(X_train)), "rows_test": int(len(X_test)), "n_features": int(X_train.shape[1]),
            "selected_model": winner, "cv_5fold_train": cv_res, "test_holdout": test_res,
            "range_ratio_p10_p90": [float(lo), float(hi)],
            "top_features_random_forest": feature_importance(fitted["random_forest"]),
        }
        bundle[group] = {"model": fitted[winner], "model_name": winner, "range_ratio": (float(lo), float(hi)),
                         "feature_columns": list(X_train.columns)}
        plots[group] = (y_test.to_numpy(), fitted[winner].predict(X_test), winner)
        t = test_res[winner]
        print(f"{group:12s} selected={winner:18s} test MAE=₹{t['MAE']:>8,.0f}  RMSE=₹{t['RMSE']:>8,.0f}  R2={t['R2']:.3f}"
              f"   (other model R2={test_res[[k for k in test_res if k != winner][0]]['R2']:.3f})")

    joblib.dump(bundle, MODEL_DIR / "resale_model.pkl")
    with open(MODEL_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({"data_note": "Trained on SYNTHETIC data (dataset/DATASET.md). Scores show the pipeline works, not real-market accuracy.",
                   "groups": metrics}, f, indent=2)

    fig, axes = plt.subplots(1, len(plots), figsize=(4 * len(plots), 3.8))
    for ax, (g, (yt, yp, name)) in zip(axes, plots.items()):
        ax.scatter(yt, yp, s=6, alpha=0.5)
        lim = [0, max(yt.max(), yp.max()) * 1.05]
        ax.plot(lim, lim, "r--", lw=1)
        ax.set_title(f"{g}\n{name.replace('_', ' ')}", fontsize=9)
        ax.set_xlabel("Actual price (₹)"); ax.set_ylabel("Predicted (₹)")
    fig.suptitle("Held-out test set: predicted vs actual (synthetic data)", fontsize=10)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "actual_vs_predicted.png", dpi=130)
    print(f"\nSaved model/resale_model.pkl, model/metrics.json, reports/actual_vs_predicted.png")


if __name__ == "__main__":
    main()
