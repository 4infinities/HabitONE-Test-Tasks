"""
Conversion crosstabs by feature level (pre-test mobile cohort).

Cohort: platform == mobile, date_reg < TEST_START.
Target: ever had successful_payment == 1.
Features: age_group, system, id_traffic_source, country_group.

Outputs:
  - outputs/conversion_crosstabs_by_feature.csv  (long, all dimensions)
  - outputs/conversion_crosstabs_pivot.csv       (wide: one block per dimension)
"""

import os

import pandas as pd
from scipy.stats import chi2_contingency

from constants import TEST_START, SCRIPT_DIR

RAW_DATA_PATH = os.path.join(SCRIPT_DIR, "..", "Raw Data.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")

DIMENSIONS = ["age_group", "system", "id_traffic_source", "country_group"]
TARGET = "converted"


def load_mobile_pre_cohort() -> pd.DataFrame:
    df = pd.read_csv(RAW_DATA_PATH)
    df["date_reg"] = pd.to_datetime(df["date_reg"])

    pre = df[(df["date_reg"] < TEST_START) & (df["platform"] == "mobile")].copy()
    payers = set(pre.loc[pre["successful_payment"] == 1, "id_user"].unique())

    users = (
        pre.sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "date_reg"] + DIMENSIONS]
    )
    users[TARGET] = users["id_user"].isin(payers).astype(int)
    return users


def crosstab_for_dimension(users: pd.DataFrame, dim: str, baseline_conv: float) -> pd.DataFrame:
    sub = users[[dim, TARGET]].dropna()
    ct = pd.crosstab(sub[dim], sub[TARGET], margins=False)
    if 0 not in ct.columns:
        ct[0] = 0
    if 1 not in ct.columns:
        ct[1] = 0
    ct = ct[[0, 1]].rename(columns={0: "non_payers", 1: "payers"})

    n_users = ct.sum(axis=1)
    out = pd.DataFrame(
        {
            "feature": dim,
            "level": ct.index.astype(str),
            "n_users": n_users.values,
            "n_payers": ct["payers"].values,
            "n_non_payers": ct["non_payers"].values,
        }
    )
    out["conversion_rate"] = out["n_payers"] / out["n_users"]
    out["pct_of_cohort"] = out["n_users"] / out["n_users"].sum()
    out["pct_of_all_payers"] = out["n_payers"] / out["n_payers"].sum()
    out["conversion_vs_baseline"] = out["conversion_rate"] - baseline_conv
    out["conversion_ratio_vs_baseline"] = out["conversion_rate"] / baseline_conv

    if sub[dim].nunique() >= 2:
        chi2, p, _, _ = chi2_contingency(pd.crosstab(sub[dim], sub[TARGET]))
        out["chi2"] = chi2
        out["chi2_pvalue"] = p
    else:
        out["chi2"] = float("nan")
        out["chi2_pvalue"] = float("nan")

    out = out.sort_values("conversion_rate", ascending=False).reset_index(drop=True)
    return out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    users = load_mobile_pre_cohort()
    baseline = users[TARGET].mean()
    n_total = len(users)
    n_payers = int(users[TARGET].sum())

    print("=== Conversion crosstabs (mobile, registered before test) ===")
    print(f"Boundary: {TEST_START}")
    print(f"Users: {n_total:,} | Payers: {n_payers:,} | Baseline conversion: {baseline:.4f}")

    frames = []
    for dim in DIMENSIONS:
        tab = crosstab_for_dimension(users, dim, baseline)
        frames.append(tab)
        print(f"\n--- {dim} (chi2 p = {tab['chi2_pvalue'].iloc[0]:.4g}) ---")
        show = tab[
            [
                "level",
                "n_users",
                "n_payers",
                "conversion_rate",
                "conversion_vs_baseline",
                "pct_of_cohort",
            ]
        ].copy()
        show["conversion_rate"] = show["conversion_rate"].map(lambda x: f"{x:.2%}")
        show["conversion_vs_baseline"] = show["conversion_vs_baseline"].map(
            lambda x: f"{x:+.2%}"
        )
        show["pct_of_cohort"] = show["pct_of_cohort"].map(lambda x: f"{x:.1%}")
        print(show.to_string(index=False))

    long_df = pd.concat(frames, ignore_index=True)
    long_path = os.path.join(OUTPUT_DIR, "conversion_crosstabs_by_feature.csv")
    long_df.to_csv(long_path, index=False, float_format="%.6f")

    # Wide pivot: rows = level, columns prefixed by feature name
    pivot_parts = []
    for dim in DIMENSIONS:
        part = long_df[long_df["feature"] == dim][
            ["level", "n_users", "n_payers", "conversion_rate"]
        ].copy()
        part = part.rename(
            columns={
                c: f"{dim}__{c}" if c != "level" else f"{dim}__level"
                for c in part.columns
            }
        )
        pivot_parts.append(part.reset_index(drop=True))

    max_len = max(len(p) for p in pivot_parts)
    for i, part in enumerate(pivot_parts):
        if len(part) < max_len:
            pivot_parts[i] = part.reindex(range(max_len))

    pivot_df = pd.concat(pivot_parts, axis=1)
    pivot_path = os.path.join(OUTPUT_DIR, "conversion_crosstabs_pivot.csv")
    pivot_df.to_csv(pivot_path, index=False, float_format="%.6f")

    summary = pd.DataFrame(
        {
            "feature": DIMENSIONS,
            "chi2_pvalue": [long_df.loc[long_df["feature"] == d, "chi2_pvalue"].iloc[0] for d in DIMENSIONS],
            "n_levels": [users[d].nunique() for d in DIMENSIONS],
            "min_conversion": [
                long_df.loc[long_df["feature"] == d, "conversion_rate"].min() for d in DIMENSIONS
            ],
            "max_conversion": [
                long_df.loc[long_df["feature"] == d, "conversion_rate"].max() for d in DIMENSIONS
            ],
            "spread_pp": [
                (
                    long_df.loc[long_df["feature"] == d, "conversion_rate"].max()
                    - long_df.loc[long_df["feature"] == d, "conversion_rate"].min()
                )
                * 100
                for d in DIMENSIONS
            ],
        }
    )
    summary_path = os.path.join(OUTPUT_DIR, "conversion_crosstabs_summary.csv")
    summary.to_csv(summary_path, index=False, float_format="%.6f")

    print(f"\nSaved: {long_path}")
    print(f"Saved: {pivot_path}")
    print(f"Saved: {summary_path}")
    print("\n--- Spread of conversion across levels (percentage points) ---")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}" if isinstance(x, float) else str(x)))


if __name__ == "__main__":
    main()
