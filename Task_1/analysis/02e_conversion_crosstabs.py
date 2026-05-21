"""
Crosstabs by feature level (pre-test mobile cohort).

Metrics per segment: conversion rate, PPU, RPU, ARPPU — each vs cohort baseline.
Cohort: platform == mobile, date_reg < TEST_START, successful payments only.
Features: age_group, system, id_traffic_source, country_group.

Outputs:
  - outputs/conversion_crosstabs_by_feature.csv  (long, all dimensions + all metrics)
  - outputs/conversion_crosstabs_summary.csv     (spread per metric per dimension)
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
    successful = pre[pre["successful_payment"] == 1]

    pay_stats = (
        successful.groupby("id_user")
        .agg(payment_count=("amount", "count"), total_revenue=("amount", "sum"))
        .reset_index()
    )

    users = (
        pre.sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "date_reg"] + DIMENSIONS]
    )
    users = users.merge(pay_stats, on="id_user", how="left")
    users["payment_count"] = users["payment_count"].fillna(0).astype(int)
    users["total_revenue"] = users["total_revenue"].fillna(0.0)
    users[TARGET] = (users["payment_count"] > 0).astype(int)
    return users


def crosstab_for_dimension(users: pd.DataFrame, dim: str, baselines: dict) -> pd.DataFrame:
    sub = users[[dim, TARGET, "payment_count", "total_revenue"]].dropna()

    grp = (
        sub.groupby(dim)
        .agg(
            n_users=(TARGET, "count"),
            n_payers=(TARGET, "sum"),
            total_payments=("payment_count", "sum"),
            total_revenue=("total_revenue", "sum"),
        )
        .reset_index()
    )

    grp["conversion_rate"] = grp["n_payers"] / grp["n_users"]
    grp["ppu"] = grp["total_payments"] / grp["n_users"]
    grp["rpu"] = grp["total_revenue"] / grp["n_users"]
    grp["arppu"] = grp["total_revenue"] / grp["n_payers"].replace(0, float("nan"))
    grp["pct_of_cohort"] = grp["n_users"] / grp["n_users"].sum()

    grp["conv_vs_baseline"] = grp["conversion_rate"] - baselines["conversion_rate"]
    grp["ppu_vs_baseline"] = grp["ppu"] - baselines["ppu"]
    grp["rpu_vs_baseline"] = grp["rpu"] - baselines["rpu"]
    grp["arppu_vs_baseline"] = grp["arppu"] - baselines["arppu"]

    if sub[dim].nunique() >= 2:
        chi2, p, _, _ = chi2_contingency(pd.crosstab(sub[dim], sub[TARGET]))
    else:
        chi2, p = float("nan"), float("nan")
    grp["chi2"] = chi2
    grp["chi2_pvalue"] = p
    grp["feature"] = dim

    grp = grp.rename(columns={dim: "level"})
    grp["level"] = grp["level"].astype(str)
    grp = grp.sort_values("conversion_rate", ascending=False).reset_index(drop=True)
    return grp


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    users = load_mobile_pre_cohort()

    baselines = {
        "conversion_rate": users[TARGET].mean(),
        "ppu": users["payment_count"].mean(),
        "rpu": users["total_revenue"].mean(),
        "arppu": users.loc[users[TARGET] == 1, "total_revenue"].mean(),
    }

    n_total = len(users)
    n_payers = int(users[TARGET].sum())
    print("=== Crosstabs (mobile, registered before test) ===")
    print(f"Boundary: {TEST_START}")
    print(f"Users: {n_total:,} | Payers: {n_payers:,}")
    print(
        f"Baseline — conv: {baselines['conversion_rate']:.4f} | "
        f"PPU: {baselines['ppu']:.4f} | "
        f"RPU: {baselines['rpu']:.4f} | "
        f"ARPPU: {baselines['arppu']:.2f}"
    )

    frames = []
    for dim in DIMENSIONS:
        tab = crosstab_for_dimension(users, dim, baselines)
        frames.append(tab)

        print(f"\n--- {dim} (chi2 p = {tab['chi2_pvalue'].iloc[0]:.4g}) ---")
        show = tab[
            ["level", "n_users", "n_payers", "pct_of_cohort",
             "conversion_rate", "conv_vs_baseline",
             "ppu", "ppu_vs_baseline",
             "rpu", "rpu_vs_baseline",
             "arppu", "arppu_vs_baseline"]
        ].copy()
        show["pct_of_cohort"] = show["pct_of_cohort"].map(lambda x: f"{x:.1%}")
        show["conversion_rate"] = show["conversion_rate"].map(lambda x: f"{x:.2%}")
        show["conv_vs_baseline"] = show["conv_vs_baseline"].map(lambda x: f"{x:+.2%}")
        show["ppu"] = show["ppu"].map(lambda x: f"{x:.4f}")
        show["ppu_vs_baseline"] = show["ppu_vs_baseline"].map(lambda x: f"{x:+.4f}")
        show["rpu"] = show["rpu"].map(lambda x: f"{x:.4f}")
        show["rpu_vs_baseline"] = show["rpu_vs_baseline"].map(lambda x: f"{x:+.4f}")
        show["arppu"] = show["arppu"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        show["arppu_vs_baseline"] = show["arppu_vs_baseline"].map(
            lambda x: f"{x:+.2f}" if pd.notna(x) else "—"
        )
        print(show.to_string(index=False))

    long_df = pd.concat(frames, ignore_index=True)
    long_path = os.path.join(OUTPUT_DIR, "conversion_crosstabs_by_feature.csv")
    long_df.to_csv(long_path, index=False, float_format="%.6f")

    metrics = ["conversion_rate", "ppu", "rpu", "arppu"]
    summary_rows = []
    for dim in DIMENSIONS:
        sub = long_df[long_df["feature"] == dim]
        row = {
            "feature": dim,
            "chi2_pvalue": sub["chi2_pvalue"].iloc[0],
            "n_levels": sub["level"].nunique(),
        }
        for m in metrics:
            row[f"{m}_min"] = sub[m].min()
            row[f"{m}_max"] = sub[m].max()
            row[f"{m}_spread"] = sub[m].max() - sub[m].min()
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    summary_path = os.path.join(OUTPUT_DIR, "conversion_crosstabs_summary.csv")
    summary.to_csv(summary_path, index=False, float_format="%.6f")

    print(f"\nSaved: {long_path}")
    print(f"Saved: {summary_path}")

    print("\n--- Spread across levels ---")
    spread_cols = ["feature"] + [f"{m}_spread" for m in metrics]
    print(summary[spread_cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
