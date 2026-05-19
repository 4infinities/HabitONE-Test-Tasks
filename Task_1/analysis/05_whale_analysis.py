"""
Step 5: Whale Distribution Analysis
A/B cohort = users registered on/after TEST_START.
Revenue = post-test successful payments aggregated to user level (0 for non-payers).
Runs for: (1) mobile-only, (2) all devices.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from constants import (
    SCRIPT_DIR,
    build_ab_user_revenue,
    load_all_payments,
    load_mobile_payments,
)

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")


def gini_coefficient(values):
    x = np.sort(np.asarray(values, dtype=float))
    x = x[x >= 0]
    n = len(x)
    if n == 0 or x.sum() == 0:
        return float("nan")
    idx = np.arange(1, n + 1)
    return (2 * (idx * x).sum() - (n + 1) * x.sum()) / (n * x.sum())



def whale_metrics(user_df, label):
    n = len(user_df)
    paying = int((user_df["revenue"] > 0).sum())
    total_rev = user_df["revenue"].sum()

    # All-user metrics (non-payers included as 0)
    mean_rpu = user_df["revenue"].mean()
    median_rpu = user_df["revenue"].median()
    mm_ratio = mean_rpu / median_rpu if median_rpu > 0 else float("inf")

    # Payer-only metrics
    payer_rev = user_df.loc[user_df["revenue"] > 0, "revenue"]
    mean_arpu = payer_rev.mean() if len(payer_rev) > 0 else float("nan")
    median_arpu = payer_rev.median() if len(payer_rev) > 0 else float("nan")
    payer_mm_ratio = mean_arpu / median_arpu if (len(payer_rev) > 0 and median_arpu > 0) else float("inf")

    gini = gini_coefficient(user_df["revenue"].values)
    gini_payers = gini_coefficient(payer_rev.values) if len(payer_rev) > 0 else float("nan")

    payer_rev_sorted = user_df.loc[user_df["revenue"] > 0, "revenue"].sort_values(ascending=False).values
    n_payers_pareto = len(payer_rev_sorted)
    if n_payers_pareto > 0:
        cumrev = np.cumsum(payer_rev_sorted)
        top_n = int((cumrev <= total_rev * 0.80).sum()) + 1
        pareto_pct = top_n / n_payers_pareto
    else:
        pareto_pct = float("nan")

    return {
        "cohort": label,
        "n_users": n,
        "paying_users": paying,
        "conversion_rate": paying / n,
        "total_revenue": total_rev,
        # all-user RPU
        "mean_rpu": mean_rpu,
        "median_rpu": median_rpu,
        "mean_median_ratio_all": mm_ratio,
        # payer-only ARPU
        "mean_arpu_payers": mean_arpu,
        "median_arpu_payers": median_arpu,
        "mean_median_ratio_payers": payer_mm_ratio,
        "gini_all": gini,
        "gini_payers": gini_payers,
        "top_pct_80pct_revenue": pareto_pct,
        "whale_model": mm_ratio > 3,
    }


def build_top_payers(ab, n=20):
    """Top-N payers with cumulative revenue % of total scenario revenue."""
    total_rev = ab["revenue"].sum()
    top = (
        ab[ab["revenue"] > 0]
        .nlargest(n, "revenue")[["id_user", "split_group", "revenue", "system", "id_traffic_source"]]
        .reset_index(drop=True)
    )
    top.index += 1
    top["cum_rev_pct"] = (top["revenue"].cumsum() / total_rev * 100).round(2)
    return top


def run(df, label, suffix):
    ab = build_ab_user_revenue(df)

    # Attach system and id_traffic_source (first row per user)
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "system", "id_traffic_source"]]
    )
    ab = ab.merge(attrs, on="id_user", how="left")

    print(f"\n{'='*55}")
    print(f"WHALE ANALYSIS: {label}")
    print(f"{'='*55}")

    overall = whale_metrics(ab, f"{label} (combined)")
    print(f"AB test users : {overall['n_users']:,}")
    print(f"Paying users  : {overall['paying_users']:,}  ({overall['conversion_rate']:.2%})")
    print(f"\n  --- All users (non-payers counted as 0) ---")
    print(f"  Mean RPU      : {overall['mean_rpu']:.4f}")
    print(f"  Median RPU    : {overall['median_rpu']:.4f}")
    print(f"  Mean/Median   : {overall['mean_median_ratio_all']:.2f}x")
    print(f"  Gini          : {overall['gini_all']:.4f}")
    print(f"\n  --- Payers only ---")
    print(f"  Mean ARPU     : {overall['mean_arpu_payers']:.4f}")
    print(f"  Median ARPU   : {overall['median_arpu_payers']:.4f}")
    print(f"  Mean/Median   : {overall['mean_median_ratio_payers']:.2f}x")
    print(f"  Gini (payers) : {overall['gini_payers']:.4f}")
    print(f"\n  Pareto (80%)  : top {overall['top_pct_80pct_revenue']:.1%} of payers -> 80% revenue")
    whale_flag = overall["whale_model"]
    print(f"  Whale model   : {'YES -> Mann-Whitney U + bootstrap + permutation' if whale_flag else 'NO -> Welch t-test'}")

    rows = [overall]
    for grp, grp_name in [(0, "Control"), (1, "Test")]:
        sub = ab[ab["split_group"] == grp]
        m = whale_metrics(sub, f"{label} -- {grp_name}")
        rows.append(m)
        print(
            f"\n  {grp_name:8s} n={m['n_users']:,}  payers={m['paying_users']:,} ({m['conversion_rate']:.2%})"
            f"\n           all-users : mean_rpu={m['mean_rpu']:.4f}  median_rpu={m['median_rpu']:.4f}  gini={m['gini_all']:.4f}"
            f"\n           payers     : mean_arpu={m['mean_arpu_payers']:.4f}  median_arpu={m['median_arpu_payers']:.4f}  gini={m['gini_payers']:.4f}"
        )

    # --- Top-20 payers ---
    top20 = build_top_payers(ab, n=20)
    print(f"\n  Top-20 payers:")
    print(top20.to_string(float_format=lambda x: f"{x:.2f}"))

    top20_path = os.path.join(OUTPUT_DIR, f"top20_payers_{suffix}.csv")
    top20.to_csv(top20_path, index=True, index_label="rank", float_format="%.2f")
    print(f"  Saved: {top20_path}")

    # Log-scale revenue distribution plot
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"Revenue Distribution (log-scale) -- {label}", fontsize=13)

    for ax, grp, grp_name, color in [
        (axes[0], 0, "Control", "steelblue"),
        (axes[1], 1, "Test", "tomato"),
    ]:
        sub_rev = ab.loc[ab["split_group"] == grp, "revenue"]
        payers_rev = sub_rev[sub_rev > 0]
        if len(payers_rev) > 0:
            ax.hist(np.log1p(payers_rev), bins=50, color=color, alpha=0.75, edgecolor="white")
        else:
            ax.text(0.5, 0.5, "No payers", ha="center", va="center", transform=ax.transAxes)
        ax.set_xlabel("log1p(Revenue)")
        ax.set_ylabel("Users")
        ax.set_title(f"{grp_name}\n{len(sub_rev):,} users total, {len(payers_rev):,} payers")

    plt.tight_layout()
    out_fig = os.path.join(OUTPUT_DIR, f"revenue_distribution_{suffix}.png")
    plt.savefig(out_fig, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_fig}")

    return pd.DataFrame(rows), ab


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    mobile_df = load_mobile_payments()
    all_df = load_all_payments()

    mobile_m, mobile_ab = run(mobile_df, "Mobile Only", "mobile")
    all_m, all_ab = run(all_df, "All Devices", "all")

    out = os.path.join(OUTPUT_DIR, "whale_metrics.csv")
    pd.concat([mobile_m, all_m], ignore_index=True).to_csv(out, index=False, float_format="%.6f")
    print(f"\nSaved: {out}")

    # --- Combined top payers: mobile vs all devices side by side ---
    top_mobile = build_top_payers(mobile_ab, n=20).rename(
        columns={"revenue": "revenue_mobile", "cum_rev_pct": "cum_rev_pct_mobile",
                 "system": "system_mobile", "id_traffic_source": "source_mobile",
                 "split_group": "group_mobile"}
    )
    top_all = build_top_payers(all_ab, n=20).rename(
        columns={"revenue": "revenue_all", "cum_rev_pct": "cum_rev_pct_all",
                 "system": "system_all", "id_traffic_source": "source_all",
                 "split_group": "group_all", "id_user": "id_user_all"}
    )
    combined = top_mobile.join(top_all, how="outer")

    print(f"\n{'='*65}")
    print("TOP-20 PAYERS: Mobile Only  vs  All Devices")
    print(f"{'='*65}")
    print(combined.to_string(float_format=lambda x: f"{x:.2f}"))

    combined_path = os.path.join(OUTPUT_DIR, "top20_payers_combined.csv")
    combined.to_csv(combined_path, index=True, index_label="rank", float_format="%.2f")
    print(f"\nSaved: {combined_path}")


if __name__ == "__main__":
    main()
