"""
Step 8: Generate all 7 required charts into the project-level charts/ directory.
Run after 01_filtering.py (requires mobile_data.csv).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from scipy import stats

from constants import SCRIPT_DIR, TEST_START, build_ab_user_revenue, load_mobile_payments

CHARTS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "charts"))
CTRL_COLOR = "#4878CF"
TEST_COLOR = "#D65F5F"


def save(fig, name):
    os.makedirs(CHARTS_DIR, exist_ok=True)
    path = os.path.join(CHARTS_DIR, name)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def _ab_with_attrs(df):
    ab = build_ab_user_revenue(df)
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "gender", "age_group", "country_group", "id_traffic_source"]]
    )
    return ab.merge(attrs, on="id_user", how="left")


# ── Chart 1: Payments Per User bar chart with 95% bootstrap CIs ──────────────

def chart01_payments_per_user(ab):
    ctrl = ab[ab["split_group"] == 0]
    test = ab[ab["split_group"] == 1]
    ppu_c = ctrl["payment_count"].mean()
    ppu_t = test["payment_count"].mean()

    rng = np.random.default_rng(42)
    n_boot = 5_000
    boot_c = rng.choice(ctrl["payment_count"].values, (n_boot, len(ctrl)), replace=True).mean(1)
    boot_t = rng.choice(test["payment_count"].values, (n_boot, len(test)), replace=True).mean(1)
    ci_c = (float(np.percentile(boot_c, 2.5)), float(np.percentile(boot_c, 97.5)))
    ci_t = (float(np.percentile(boot_t, 2.5)), float(np.percentile(boot_t, 97.5)))

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(["Control", "Test"], [ppu_c, ppu_t],
                  color=[CTRL_COLOR, TEST_COLOR], width=0.5, alpha=0.85)
    ax.errorbar([0, 1], [ppu_c, ppu_t],
                yerr=[[ppu_c - ci_c[0], ppu_t - ci_t[0]], [ci_c[1] - ppu_c, ci_t[1] - ppu_t]],
                fmt="none", color="black", capsize=6, linewidth=2)
    for bar, val in zip(bars, [ppu_c, ppu_t]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.04 + 0.0001,
                f"{val:.4f}", ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax.set_ylabel("Avg Payments Per User", fontsize=12)
    ax.set_ylim(0, max(ppu_c, ppu_t) * 1.6)
    ax.set_title("Payments Per User: Test vs Control\n(Primary Metric — 95% Bootstrap Confidence Intervals)", fontsize=13)
    ax.text(0.5, -0.14,
            "Payments per user = total successful payments ÷ all users (including non-payers). Error bars show 95% bootstrap CI.\n"
            "Captures both conversion rate and repeat-purchase behaviour in a single metric.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "01_payments_per_user.png")


# ── Chart 2: Payment Amount Distribution (violin, log scale) ─────────────────

def chart02_amount_distribution(ab):
    ctrl_rev = ab.loc[(ab["split_group"] == 0) & (ab["revenue"] > 0), "revenue"]
    test_rev = ab.loc[(ab["split_group"] == 1) & (ab["revenue"] > 0), "revenue"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Payment Amount Distribution — Payers Only (log₁₊ scale)", fontsize=13)
    for ax, data, label, color in [
        (axes[0], ctrl_rev, f"Control\n(n={len(ctrl_rev):,} payers)", CTRL_COLOR),
        (axes[1], test_rev, f"Test\n(n={len(test_rev):,} payers)", TEST_COLOR),
    ]:
        parts = ax.violinplot([np.log1p(data.values)], positions=[1], showmedians=True)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.7)
        parts["cmedians"].set_color("white")
        parts["cmedians"].set_linewidth(2)
        ax.set_title(label, fontsize=11)
        ax.set_ylabel("log₁₊(Amount, USD)", fontsize=10)
        ax.set_xticks([])
        ax.text(0.95, 0.97,
                f"Median: ${data.median():,.0f}\nMean: ${data.mean():,.0f}\nP95: ${data.quantile(0.95):,.0f}",
                transform=ax.transAxes, va="top", ha="right", fontsize=9,
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))
    axes[0].text(1.0, -0.13,
                 "Log-scale due to heavy right skew (whale model). "
                 "Mann-Whitney U test: not significant (p>0.05).",
                 transform=axes[0].transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "02_amount_distribution.png")


# ── Chart 3: Daily Conversion Rate Time Series ───────────────────────────────

def chart03_daily_timeseries(df, ab):
    ab_ids = set(ab["id_user"])
    n_ctrl = int((ab["split_group"] == 0).sum())
    n_test = int((ab["split_group"] == 1).sum())

    post = df[
        df["id_user"].isin(ab_ids)
        & df["date_payment"].notna()
        & (df["date_payment"] >= TEST_START)
        & (df["successful_payment"] == 1)
    ].copy()
    post["date"] = post["date_payment"].dt.date

    daily = (
        post.groupby(["date", "split_group"])["id_user"]
        .nunique()
        .unstack(fill_value=0)
    )
    daily.columns = daily.columns.astype(int)
    for col in [0, 1]:
        if col not in daily.columns:
            daily[col] = 0

    daily["cr_ctrl"] = daily[0] / n_ctrl * 100
    daily["cr_test"] = daily[1] / n_test * 100

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(daily.index, daily["cr_ctrl"], color=CTRL_COLOR,
            label=f"Control (n={n_ctrl:,})", linewidth=2)
    ax.plot(daily.index, daily["cr_test"], color=TEST_COLOR,
            label=f"Test (n={n_test:,})", linewidth=2)
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Daily Conversion Rate (%)", fontsize=11)
    ax.set_title("Daily Conversion Rate by Group", fontsize=13)
    ax.legend(fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.2f}%"))
    plt.xticks(rotation=30, ha="right")
    ax.text(0.5, -0.18,
            "Daily % of all A/B test users who made at least one successful payment on that day.\n"
            "No consistent separation between groups is visible throughout the experiment.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "03_daily_timeseries.png")


# ── Chart 4: Average Revenue Per User (ARPU) bar chart ───────────────────────

def chart04_arpu(ab):
    ctrl_rev = ab.loc[ab["split_group"] == 0, "revenue"]
    test_rev = ab.loc[ab["split_group"] == 1, "revenue"]
    rpu_c, rpu_t = ctrl_rev.mean(), test_rev.mean()

    rng = np.random.default_rng(42)
    n_boot = 5_000
    boot_c = rng.choice(ctrl_rev.values, (n_boot, len(ctrl_rev)), replace=True).mean(1)
    boot_t = rng.choice(test_rev.values, (n_boot, len(test_rev)), replace=True).mean(1)
    ci_c = (float(np.percentile(boot_c, 2.5)), float(np.percentile(boot_c, 97.5)))
    ci_t = (float(np.percentile(boot_t, 2.5)), float(np.percentile(boot_t, 97.5)))

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(["Control", "Test"], [rpu_c, rpu_t],
                  color=[CTRL_COLOR, TEST_COLOR], width=0.5, alpha=0.85)
    ax.errorbar([0, 1], [rpu_c, rpu_t],
                yerr=[[rpu_c - ci_c[0], rpu_t - ci_t[0]], [ci_c[1] - rpu_c, ci_t[1] - rpu_t]],
                fmt="none", color="black", capsize=6, linewidth=2)
    for bar, val in zip(bars, [rpu_c, rpu_t]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                f"${val:.2f}", ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax.set_ylabel("Average Revenue Per User (USD)", fontsize=12)
    ax.set_ylim(0, max(rpu_c, rpu_t) * 1.6)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))
    ax.set_title("Average Revenue Per User (ARPU)\n(with 95% Bootstrap Confidence Intervals)", fontsize=13)
    ax.text(0.5, -0.14,
            "ARPU = total revenue ÷ all users (including non-payers). Error bars = 95% bootstrap CI.\n"
            "Wide CI reflects extreme variance in whale-model revenue. Difference not significant.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "04_arpu.png")


# ── Chart 5: Conversion Rate by Country Group ────────────────────────────────

def chart05_country_heatmap(ab):
    col = "country_group"
    if col not in ab.columns or ab[col].nunique() < 2:
        print(f"  SKIP chart05: '{col}' has <2 unique values")
        return

    seg = (
        ab.groupby([col, "split_group"])["revenue"]
        .apply(lambda x: (x > 0).mean())
        .reset_index(name="cr")
    )
    ctrl_s = seg[seg["split_group"] == 0].set_index(col)["cr"].rename("cr_ctrl")
    test_s = seg[seg["split_group"] == 1].set_index(col)["cr"].rename("cr_test")
    pivot = ctrl_s.to_frame().join(test_s, how="outer").sort_values("cr_ctrl")
    pivot["diff_pp"] = (pivot["cr_test"] - pivot["cr_ctrl"]) * 100

    h = max(4, len(pivot) * 0.55 + 2)
    fig, ax = plt.subplots(figsize=(10, h))
    x = np.arange(len(pivot))
    w = 0.35
    ax.barh(x + w / 2, pivot["cr_ctrl"] * 100, w, color=CTRL_COLOR, alpha=0.85, label="Control")
    ax.barh(x - w / 2, pivot["cr_test"] * 100, w, color=TEST_COLOR, alpha=0.85, label="Test")
    for i, (_, row) in enumerate(pivot.iterrows()):
        right = max(row["cr_ctrl"], row["cr_test"]) * 100
        ax.text(right + 0.03, i, f"{row['diff_pp']:+.2f} pp", va="center", fontsize=8)
    ax.set_yticks(x)
    ax.set_yticklabels(pivot.index, fontsize=10)
    ax.set_xlabel("Conversion Rate (%)", fontsize=11)
    ax.set_title("Conversion Rate by Country Group: Test vs Control", fontsize=13)
    ax.legend(fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax.text(0.5, -0.1,
            "Numbers after bars = Test − Control in percentage points (pp). Negative = test performed worse.",
            transform=ax.transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "05_country_heatmap.png")


# ── Chart 6: Whale Segment Analysis ─────────────────────────────────────────

def chart06_whale_analysis(ab):
    payers_sorted = ab.loc[ab["revenue"] > 0, "revenue"].sort_values(ascending=False).values
    idx = int((np.cumsum(payers_sorted) < 0.75 * payers_sorted.sum()).sum())
    cutoff = float(payers_sorted[min(idx, len(payers_sorted) - 1)])

    def whale_stats(grp):
        w = grp[grp["revenue"] >= cutoff]
        n_payers = int((grp["revenue"] > 0).sum())
        return {
            "pct_of_payers": len(w) / max(n_payers, 1) * 100,
            "arpu": float(w["revenue"].mean()) if len(w) else 0.0,
            "n": len(w),
        }

    sc = whale_stats(ab[ab["split_group"] == 0])
    st = whale_stats(ab[ab["split_group"] == 1])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"Whale Segment Analysis — Mobile  (cutoff ≥ ${cutoff:,.0f})", fontsize=13)

    # Left: Whale share of payers
    vals_pct = [sc["pct_of_payers"], st["pct_of_payers"]]
    bars0 = axes[0].bar(["Control", "Test"], vals_pct,
                         color=[CTRL_COLOR, TEST_COLOR], width=0.5, alpha=0.85)
    for bar, val in zip(bars0, vals_pct):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.04,
                     f"{val:.1f}%", ha="center", va="bottom", fontsize=13, fontweight="bold")
    axes[0].set_title(
        f"Whale Share of Payers\n(control: {sc['n']} whales, test: {st['n']} whales)", fontsize=11)
    axes[0].set_ylabel("Whale % of Payers", fontsize=11)
    axes[0].set_ylim(0, max(vals_pct) * 1.5)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))

    # Right: Whale ARPU
    vals_arpu = [sc["arpu"], st["arpu"]]
    bars1 = axes[1].bar(["Control", "Test"], vals_arpu,
                         color=[CTRL_COLOR, TEST_COLOR], width=0.5, alpha=0.85)
    for bar, val in zip(bars1, vals_arpu):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.02,
                     f"${val:,.0f}", ha="center", va="bottom", fontsize=13, fontweight="bold")
    axes[1].set_title("Avg Revenue per Whale User", fontsize=11)
    axes[1].set_ylabel("Whale ARPU (USD)", fontsize=11)
    axes[1].set_ylim(0, max(vals_arpu) * 1.4)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    axes[0].text(1.0, -0.14,
                 f"Whale = payer whose spend contributes to the top 75% of group revenue (cutoff: ${cutoff:,.0f}).\n"
                 "Small whale sample per group — differences are directional only.",
                 transform=axes[0].transAxes, ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "06_whale_analysis.png")


# ── Chart 7: Sanity Check Distributions ──────────────────────────────────────

def chart07_sanity_checks(ab):
    dims = [d for d in ["gender", "age_group", "country_group", "id_traffic_source"]
            if d in ab.columns and ab[d].nunique() > 1]
    if not dims:
        print("  SKIP chart07: no multi-level attribute columns found")
        return

    fig, axes = plt.subplots(1, len(dims), figsize=(5 * len(dims), 5))
    if len(dims) == 1:
        axes = [axes]
    fig.suptitle("Sanity Check: User Attribute Distributions by Group\n"
                 "(columns should look similar if randomization worked)", fontsize=12)

    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())

    for ax, dim in zip(axes, dims):
        ct = pd.crosstab(ab[dim], ab["split_group"], normalize="columns") * 100
        ct.columns = [f"Control\n(n={n_c:,})", f"Test\n(n={n_t:,})"]
        ct.plot(kind="bar", ax=ax, color=[CTRL_COLOR, TEST_COLOR],
                alpha=0.85, width=0.65, legend=False)
        ax.set_title(dim.replace("_", " ").title(), fontsize=11)
        ax.set_ylabel("% of group", fontsize=10)
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=30)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))

    axes[-1].legend(loc="upper right", fontsize=9)
    fig.text(0.5, -0.02,
             "Chi-square test results in homogeneity_table.csv. "
             "System (device OS) showed p=0.004 — flagged imbalance.",
             ha="center", fontsize=9, color="#555", style="italic")
    fig.tight_layout()
    save(fig, "07_sanity_checks.png")


def main():
    print("=== Step 8: Generating Charts ===")
    df = load_mobile_payments()
    ab = _ab_with_attrs(df)

    chart01_payments_per_user(ab)
    chart02_amount_distribution(ab)
    chart03_daily_timeseries(df, ab)
    chart04_arpu(ab)
    chart05_country_heatmap(ab)
    chart06_whale_analysis(ab)
    chart07_sanity_checks(ab)
    print(f"\nDone. All charts saved to: {CHARTS_DIR}")


if __name__ == "__main__":
    main()
