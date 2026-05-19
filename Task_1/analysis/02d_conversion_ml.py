"""
Conversion drivers (explanatory): logistic regression, random forest, XGBoost.

Cohorts (date_reg < TEST_START):
  - all: every platform in Raw Data
  - mobile: platform == 'mobile' only (desktop/other excluded)

Target: ever had successful_payment == 1 (full observation window).
split_group excluded (constant 0 for pre-test users).

Goal: identify which registration attributes associate with paying;
if id_traffic_source dominates, that is the main factor to stratify/control
for randomization checks — not a causal proof, but sufficient for confound control.

Optional time-based CV (not run by default):
  Sort users by date_reg; train on earliest 70%, test on latest 30%.
  Same features/target; reports whether drivers are stable over registration time.

Outputs (analysis/outputs/):
  - conversion_ml_{cohort}_logistic_coefficients.csv
  - conversion_ml_{cohort}_rf_importances.csv
  - conversion_ml_{cohort}_xgb_importances.csv
  - conversion_ml_{cohort}_model_metrics.csv  (precision/recall per class for logit + xgb)
  - conversion_ml_traffic_source_share.csv    (share of total importance by cohort/model)
"""

import os

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from constants import TEST_START, SCRIPT_DIR

RAW_DATA_PATH = os.path.join(SCRIPT_DIR, "..", "Raw Data.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")

BASE_FEATURES = [
    "gender",
    "id_traffic_source",
    "country_group",
    "age_group",
    "system",
]
ALL_FEATURES = ["platform"] + BASE_FEATURES
TARGET = "converted"
TRAFFIC_PREFIX = "cat__id_traffic_source_"


def load_user_cohort(platform_filter: str | None = None) -> pd.DataFrame:
    """One row per user registered before TEST_START; optional platform filter."""
    df = pd.read_csv(RAW_DATA_PATH)
    df["date_reg"] = pd.to_datetime(df["date_reg"])
    df["date_payment"] = pd.to_datetime(df["date_payment"], errors="coerce")

    pre = df[df["date_reg"] < TEST_START].copy()
    if platform_filter:
        pre = pre[pre["platform"] == platform_filter]

    payers = set(pre.loc[pre["successful_payment"] == 1, "id_user"].unique())
    attr_cols = ["id_user", "platform", "split_group", "date_reg"] + BASE_FEATURES
    users = (
        pre.sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[attr_cols]
    )
    users[TARGET] = users["id_user"].isin(payers).astype(int)
    return users


def features_for_cohort(cohort: str) -> list[str]:
    return BASE_FEATURES if cohort == "mobile" else ALL_FEATURES


def _make_ohe_transformer(feature_cols: list[str], drop) -> ColumnTransformer:
    cat_features = [c for c in ["gender", "platform", "id_traffic_source", "system"] if c in feature_cols]
    num_as_cat = [c for c in ["country_group", "age_group"] if c in feature_cols]
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False, drop=drop),
                cat_features + num_as_cat,
            ),
        ],
        remainder="drop",
    )


def build_preprocessor_logistic(feature_cols: list[str]) -> ColumnTransformer:
    """drop='first' removes one dummy per category to avoid perfect multicollinearity."""
    return _make_ohe_transformer(feature_cols, drop="first")


def build_preprocessor_tree(feature_cols: list[str]) -> ColumnTransformer:
    """drop=None: trees don't need dummy-variable trap avoidance; all levels visible."""
    return _make_ohe_transformer(feature_cols, drop=None)


def feature_names(preprocessor: ColumnTransformer) -> list[str]:
    return list(preprocessor.get_feature_names_out())


def fit_logistic(X_train, y_train, feature_cols):
    preprocessor = build_preprocessor_logistic(feature_cols)
    pipe = Pipeline(
        [
            ("prep", preprocessor),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
            ),
        ]
    )
    pipe.fit(X_train, y_train)
    return pipe


def fit_random_forest(X_train, y_train, feature_cols):
    preprocessor = build_preprocessor_tree(feature_cols)
    pipe = Pipeline(
        [
            ("prep", preprocessor),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=12,
                    min_samples_leaf=20,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipe.fit(X_train, y_train)
    return pipe


def fit_xgboost(X_train, y_train, feature_cols):
    preprocessor = build_preprocessor_tree(feature_cols)
    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    scale_pos_weight = n_neg / n_pos if n_pos else 1.0
    pipe = Pipeline(
        [
            ("prep", preprocessor),
            (
                "model",
                XGBClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    scale_pos_weight=scale_pos_weight,
                    eval_metric="logloss",
                    importance_type="gain",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipe.fit(X_train, y_train)
    return pipe


def importance_frame(names: list[str], values: np.ndarray) -> pd.DataFrame:
    out = pd.DataFrame({"feature": names, "importance": values})
    out["abs_importance"] = out["importance"].abs()
    return out.sort_values("abs_importance", ascending=False).reset_index(drop=True)


def evaluate_classifier(name: str, y_test, proba, threshold: float = 0.5) -> dict:
    pred = (proba >= threshold).astype(int)
    prec, rec, f1_scores, _ = precision_recall_fscore_support(
        y_test, pred, labels=[0, 1], zero_division=0
    )
    p0, p1 = prec[0], prec[1]
    r0, r1 = rec[0], rec[1]
    f0, f1_payer = f1_scores[0], f1_scores[1]
    return {
        "cohort": "",
        "model": name,
        "threshold": threshold,
        "auc_roc": roc_auc_score(y_test, proba),
        "accuracy": accuracy_score(y_test, pred),
        "precision_non_payer": p0,
        "recall_non_payer": r0,
        "f1_non_payer": f0,
        "precision_payer": p1,
        "recall_payer": r1,
        "f1_payer": f1_payer,
        "n_test": len(y_test),
        "n_test_payers": int(y_test.sum()),
    }


def traffic_source_share(importance_df: pd.DataFrame) -> float:
    total = importance_df["abs_importance"].sum()
    if total == 0:
        return float("nan")
    traffic = importance_df.loc[
        importance_df["feature"].str.startswith(TRAFFIC_PREFIX), "abs_importance"
    ].sum()
    return traffic / total


def print_coef_summary(coef_df: pd.DataFrame) -> None:
    print("\nLogistic - top positive drivers:")
    print(
        coef_df[coef_df["importance"] > 0]
        .sort_values("importance", ascending=False)
        .head(8)
        .to_string(index=False)
    )
    print("\nLogistic - top negative drivers:")
    print(
        coef_df[coef_df["importance"] < 0]
        .sort_values("importance")
        .head(8)
        .to_string(index=False)
    )


def run_cohort(cohort: str, users: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_cols = features_for_cohort(cohort)
    print(f"\n{'=' * 60}")
    print(f"COHORT: {cohort.upper()} | features: {feature_cols}")
    print(f"Users: {len(users):,} | conversion: {users[TARGET].mean():.4f} ({users[TARGET].sum():,} payers)")

    X = users[feature_cols].astype(str)
    y = users[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train: {len(X_train):,} | Test: {len(X_test):,}")

    log_pipe = fit_logistic(X_train, y_train, feature_cols)
    log_proba = log_pipe.predict_proba(X_test)[:, 1]
    log_names = feature_names(log_pipe.named_steps["prep"])
    coef_df = importance_frame(log_names, log_pipe.named_steps["model"].coef_[0])
    coef_path = os.path.join(OUTPUT_DIR, f"conversion_ml_{cohort}_logistic_coefficients.csv")
    coef_df.to_csv(coef_path, index=False)
    print_coef_summary(coef_df)
    print(f"Saved: {coef_path}")

    rf_pipe = fit_random_forest(X_train, y_train, feature_cols)
    rf_proba = rf_pipe.predict_proba(X_test)[:, 1]
    rf_df = importance_frame(
        feature_names(rf_pipe.named_steps["prep"]),
        rf_pipe.named_steps["model"].feature_importances_,
    )
    rf_path = os.path.join(OUTPUT_DIR, f"conversion_ml_{cohort}_rf_importances.csv")
    rf_df.to_csv(rf_path, index=False)
    print("\nRandom forest - top features:")
    print(rf_df.head(10).to_string(index=False))
    print(f"Saved: {rf_path}")

    xgb_pipe = fit_xgboost(X_train, y_train, feature_cols)
    xgb_proba = xgb_pipe.predict_proba(X_test)[:, 1]
    xgb_df = importance_frame(
        feature_names(xgb_pipe.named_steps["prep"]),
        xgb_pipe.named_steps["model"].feature_importances_,
    )
    xgb_path = os.path.join(OUTPUT_DIR, f"conversion_ml_{cohort}_xgb_importances.csv")
    xgb_df.to_csv(xgb_path, index=False)
    print("\nXGBoost - top features:")
    print(xgb_df.head(10).to_string(index=False))
    print(f"Saved: {xgb_path}")

    metrics = [
        evaluate_classifier("logistic_regression", y_test, log_proba),
        evaluate_classifier("random_forest", y_test, rf_proba),
        evaluate_classifier("xgboost", y_test, xgb_proba),
    ]
    for row in metrics:
        row["cohort"] = cohort
    metrics_df = pd.DataFrame(metrics)
    metrics_path = os.path.join(OUTPUT_DIR, f"conversion_ml_{cohort}_model_metrics.csv")
    metrics_df.to_csv(metrics_path, index=False)

    print("\n--- Hold-out metrics (threshold=0.5) ---")
    show = metrics_df[
        [
            "model",
            "auc_roc",
            "accuracy",
            "precision_non_payer",
            "recall_non_payer",
            "precision_payer",
            "recall_payer",
            "f1_payer",
        ]
    ]
    print(show.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"Saved: {metrics_path}")

    share_rows = []
    for model_name, imp_df in [
        ("logistic_regression", coef_df),
        ("random_forest", rf_df),
        ("xgboost", xgb_df),
    ]:
        share = traffic_source_share(imp_df)
        share_rows.append(
            {
                "cohort": cohort,
                "model": model_name,
                "traffic_source_importance_share": share,
                "top_feature": imp_df.iloc[0]["feature"],
                "top_feature_importance": imp_df.iloc[0]["abs_importance"],
            }
        )
    share_df = pd.DataFrame(share_rows)
    print("\n--- Traffic source share of total |importance| ---")
    print(share_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    return metrics_df, share_df


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== Conversion ML (explanatory) ===")
    print(f"Test boundary: {TEST_START}")
    print("Target: ever successful payment | split_group ignored")

    users_all = load_user_cohort()
    users_mobile = load_user_cohort(platform_filter="mobile")

    all_metrics, all_share = run_cohort("all", users_all)
    mob_metrics, mob_share = run_cohort("mobile", users_mobile)

    combined_metrics = pd.concat([all_metrics, mob_metrics], ignore_index=True)
    combined_share = pd.concat([all_share, mob_share], ignore_index=True)
    combined_metrics.to_csv(
        os.path.join(OUTPUT_DIR, "conversion_ml_model_metrics.csv"), index=False
    )
    combined_share.to_csv(
        os.path.join(OUTPUT_DIR, "conversion_ml_traffic_source_share.csv"), index=False
    )

    print(f"\n{'=' * 60}")
    print("SUMMARY: traffic source as randomization control factor")
    print(combined_share.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(
        "\nIf traffic_source_importance_share is high across cohorts/models,"
        "\nstratifying or checking balance on id_traffic_source is the main control needed."
    )
    print("\nTime-based CV (optional, not run): sort by date_reg, train earliest 70%,")
    print("test latest 30% — same pipeline; compare importances to this random split.")


if __name__ == "__main__":
    main()
