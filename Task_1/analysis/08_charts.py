"""
Step 8: Generate all charts — professional design.
Seaborn whitegrid theme + Segoe UI font for clean, report-ready output.

Combined PNGs (1×2 or 2×2 subplots) so each report block shows two charts side by side,
the same way as the whale analysis panel.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.stats.proportion import proportion_confint

from constants import SCRIPT_DIR, TEST_START, build_ab_user_revenue, load_mobile_payments

CHARTS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "charts"))

CTRL_COLOR = "#4B6FA5"      # slate blue
TEST_COLOR  = "#E88C30"      # warm amber
ANNOTATION_COLOR = "#555555"
GROUP_LABELS = {0: "Control", 1: "Test"}


def _setup_style():
    sns.set_theme(style="whitegrid", font_scale=1.05)
    plt.rcParams.update({
        "font.family": "Segoe UI",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.alpha": 0.35,
        "grid.linestyle": "--",
    })


def save(fig, name):
    os.makedirs(CHARTS_DIR, exist_ok=True)
    path = os.path.join(CHARTS_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def _ab_with_attrs(df):
    ab = build_ab_user_revenue(df)
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "gender", "age_group", "country_group", "id_traffic_source", "system"]]
    )
    return ab.merge(attrs, on="id_user", how="left")


def _bootstrap_ci(values, n_boot=5_000, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)
    boots = rng.choice(values, (n_boot, len(values)), replace=True).mean(1)
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _prop_ci(count, n, alpha=0.05):
    if n == 0:
        return 0.0, 0.0
    lo, hi = proportion_confint(int(count), int(n), alpha=alpha, method="wilson")
    return float(lo), float(hi)


def _bar_panel(ax, series_c, series_t, ylabel, title, val_fmt="{:.4f}", rng=None):
    """Reusable: draws a two-bar (Control / Test) plot with bootstrap CIs on ax."""
    if rng is None:
        rng = np.random.default_rng(42)
    means = [series_c.mean(), series_t.mean()]
    cis   = [_bootstrap_ci(s.values, rng=rng) for s in [series_c, series_t]]
    n_c, n_t = len(series_c), len(series_t)

    bars = ax.bar(["Control", "Test"], means,
                  color=[CTRL_COLOR, TEST_COLOR], width=0.45, zorder=3)
    ax.errorbar(
        [0, 1], means,
        yerr=[[m - ci[0] for m, ci in zip(means, cis)],
              [ci[1] - m for m, ci in zip(means, cis)]],
        fmt="none", color="#222", capsize=7, linewidth=1.8, zorder=4,
    )
    for bar, val, ci in zip(bars, means, cis):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            ci[1] + max(means) * 0.04,
            val_fmt.format(val),
            ha="center", va="bottom", fontsize=13, fontweight="bold",
        )
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_ylim(0, max(ci[1] for ci in cis) * 1.45)
    ax.set_title(title, fontsize=11, pad=10)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([f"Control\nn={n_c:,}", f"Test\nn={n_t:,}"], fontsize=11)
    return means, cis


# ── Chart 01: Primary Metrics — PPU + RPU side by side ───────────────────────

def chart01_primary_metrics(ab):
    rng = np.random.default_rng(42)
    ctrl = ab[ab["split_group"] == 0]
    test = ab[ab["split_group"] == 1]

    _, p_ppu = stats.mannwhitneyu(
        test["payment_count"], ctrl["payment_count"], alternative="greater")
    _, p_rpu = stats.mannwhitneyu(
        test["revenue"], ctrl["revenue"], alternative="greater")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Primary Metrics: Test vs Control — Mobile A/B Test",
                 fontsize=13, y=1.02)

    _bar_panel(
        axes[0], ctrl["payment_count"], test["payment_count"],
        "Avg Payments Per User",
        f"Payments Per User (PPU) [PRIMARY]\nNot significant — p = {p_ppu:.3f}",
        val_fmt="{:.4f}", rng=rng,
    )

    means_rpu, cis_rpu = _bar_panel(
        axes[1], ctrl["revenue"], test["revenue"],
        "Avg Revenue Per User (USD)",
        f"Revenue Per User (RPU)\nNot significant — p = {p_rpu:.3f}",
        val_fmt="${:.2f}", rng=rng,
    )
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.16)
    fig.text(
        0.5, 0.01,
        "Error bars = 95% bootstrap CI.  "
        "PPU captures both conversion and repeat purchases (denominator = all users).  "
        "RPU includes non-payers.",
        ha="center", fontsize=8.5, color=ANNOTATION_COLOR, style="italic",
    )
    save(fig, "01_primary_metrics.png")


# ── Chart 02+03: Amount Distribution + Daily Timeseries ──────────────────────

def chart02_03_amount_trend(ab, df):
    ctrl_payers = ab[(ab["split_group"] == 0) & (ab["revenue"] > 0)]["revenue"]
    test_payers = ab[(ab["split_group"] == 1) & (ab["revenue"] > 0)]["revenue"]
    _, p_arpp = stats.mannwhitneyu(test_payers, ctrl_payers, alternative="greater")

    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())
    ab_ids = set(ab["id_user"])

    # Daily conversion series
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
    daily["cr_ctrl"] = daily[0] / n_c * 100
    daily["cr_test"] = daily[1] / n_t * 100

    fig, axes = plt.subplots(
        1, 2, figsize=(17, 5),
        gridspec_kw={"width_ratios": [2, 3]},
    )
    fig.suptitle("Payment Amount Distribution & Daily Conversion Trend",
                 fontsize=13, y=1.02)

    # ── Left: key percentile bars (log scale) ──
    ax = axes[0]
    labels = ["P25", "Median", "P75", "P90", "P95"]
    qs     = [0.25, 0.50, 0.75, 0.90, 0.95]
    ctrl_vals = [ctrl_payers.quantile(q) for q in qs]
    test_vals  = [test_payers.quantile(q) for q in qs]

    x = np.arange(len(labels))
    w = 0.35
    bars_c = ax.bar(x - w / 2, ctrl_vals, w,
                    label=f"Control ({len(ctrl_payers):,} payers)",
                    color=CTRL_COLOR, zorder=3)
    bars_t = ax.bar(x + w / 2, test_vals, w,
                    label=f"Test ({len(test_payers):,} payers)",
                    color=TEST_COLOR, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_ylabel("Amount (USD, log scale)", fontsize=10)
    ax.set_title(
        f"Payment Amount Percentiles — Payers Only\nMann-Whitney U: p = {p_arpp:.3f} (not significant)",
        fontsize=11, pad=10,
    )
    ax.legend(fontsize=9, framealpha=0.9)
    ax.grid(axis="y", alpha=0.35, linestyle="--")
    ax.grid(axis="x", visible=False)

    # ── Right: daily timeseries ──
    ax2 = axes[1]
    ax2.plot(daily.index, daily["cr_ctrl"], color=CTRL_COLOR,
             label=f"Control (n={n_c:,})", linewidth=2, zorder=3)
    ax2.plot(daily.index, daily["cr_test"], color=TEST_COLOR,
             label=f"Test (n={n_t:,})", linewidth=2, zorder=3)
    ax2.fill_between(daily.index, daily["cr_ctrl"], daily["cr_test"],
                     alpha=0.08, color="#888")
    ax2.set_ylabel("Daily Conversion Rate (%)", fontsize=11)
    ax2.set_title("Daily Conversion Rate by Group\n(July 23 – Aug 21, 2021)",
                  fontsize=11, pad=10)
    ax2.legend(fontsize=10, framealpha=0.9)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.2f}%"))
    ax2.grid(axis="y", alpha=0.35, linestyle="--")
    ax2.grid(axis="x", visible=False)
    fig.autofmt_xdate(rotation=30, ha="right")

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)
    fig.text(
        0.5, 0.02,
        "Left: log scale used due to heavy right skew (whale model).  "
        "Right: daily % of A/B cohort with ≥1 successful payment — no consistent trend visible.",
        ha="center", fontsize=8.5, color=ANNOTATION_COLOR, style="italic",
    )
    save(fig, "02_amount_and_trend.png")


# ── Chart 05: Conversion Rate by Country Group ────────────────────────────────

def chart05_country_heatmap(ab):
    col = "country_group"
    if col not in ab.columns or ab[col].nunique() < 2:
        print(f"  SKIP chart05: '{col}' has <2 unique values")
        return

    seg = (
        ab.groupby([col, "split_group"])
        .agg(conv=("revenue", lambda x: (x > 0).sum()), n=("revenue", "count"))
        .reset_index()
    )
    seg["cr"]    = seg["conv"] / seg["n"]
    seg["ci_lo"] = seg.apply(lambda r: _prop_ci(r["conv"], r["n"])[0], axis=1)
    seg["ci_hi"] = seg.apply(lambda r: _prop_ci(r["conv"], r["n"])[1], axis=1)

    ctrl = seg[seg["split_group"] == 0].set_index(col)
    test = seg[seg["split_group"] == 1].set_index(col)
    groups = sorted(set(ctrl.index) | set(test.index),
                    key=lambda g: ctrl.loc[g, "cr"] if g in ctrl.index else 0)

    fig, ax = plt.subplots(figsize=(11, max(4, len(groups) * 0.8 + 2)))
    x = np.arange(len(groups))
    w = 0.35

    for i, g in enumerate(groups):
        for offset, src, color, label in [
            (w / 2, ctrl, CTRL_COLOR, "Control"),
            (-w / 2, test, TEST_COLOR, "Test"),
        ]:
            if g not in src.index:
                continue
            row = src.loc[g]
            cr_pct = row["cr"] * 100
            xerr_lo = (row["cr"] - row["ci_lo"]) * 100
            xerr_hi = (row["ci_hi"] - row["cr"]) * 100
            ax.barh(i + offset, cr_pct, w, color=color, alpha=0.88,
                    label=label if i == 0 else "_", zorder=3)
            ax.errorbar(cr_pct, i + offset,
                        xerr=[[xerr_lo], [xerr_hi]],
                        fmt="none", color="#222", capsize=4, linewidth=1.4, zorder=4)

    x_max = max(
        max(ctrl.loc[g, "cr"] if g in ctrl.index else 0 for g in groups),
        max(test.loc[g, "cr"] if g in test.index else 0 for g in groups),
    ) * 100

    for i, g in enumerate(groups):
        if g in ctrl.index and g in test.index:
            diff = (test.loc[g, "cr"] - ctrl.loc[g, "cr"]) * 100
            color = TEST_COLOR if diff > 0 else CTRL_COLOR
            ax.text(x_max * 1.03, i, f"{diff:+.2f} pp",
                    va="center", fontsize=9, fontweight="bold", color=color)

    ax.set_yticks(x)
    ax.set_yticklabels([f"Group {g}" for g in groups], fontsize=11)
    ax.set_xlabel("Conversion Rate (%)", fontsize=11, labelpad=8)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.set_title(
        "Conversion Rate by Country Group: Test vs Control\n"
        "Error bars = 95% Wilson CI (overlapping CIs → not significant)",
        fontsize=12, pad=12,
    )
    ax.legend(fontsize=10, loc="lower right", framealpha=0.9)
    ax.set_xlim(0, x_max * 1.2)
    ax.grid(axis="x", alpha=0.35, linestyle="--")
    ax.grid(axis="y", visible=False)

    fig.subplots_adjust(bottom=0.17)
    fig.text(
        0.5, 0.03,
        "Numbers to the right = Test − Control in pp.  "
        "Overlapping CIs indicate the difference is not statistically significant.",
        ha="center", fontsize=8.5, color=ANNOTATION_COLOR, style="italic",
    )
    save(fig, "05_country_heatmap.png")


# ── Chart 06: Whale Segment — share of payers + avg revenue ──────────────────

def chart06_whale_analysis(ab):
    payers_sorted = ab.loc[ab["revenue"] > 0, "revenue"].sort_values(ascending=False).values
    idx    = int((np.cumsum(payers_sorted) < 0.75 * payers_sorted.sum()).sum())
    cutoff = float(payers_sorted[min(idx, len(payers_sorted) - 1)])

    def whale_stats(grp):
        w        = grp[grp["revenue"] >= cutoff]
        n_payers = int((grp["revenue"] > 0).sum())
        n_w      = len(w)
        pct      = n_w / max(n_payers, 1) * 100
        ci_lo, ci_hi = _prop_ci(n_w, n_payers)
        arpu     = float(w["revenue"].mean()) if n_w else 0.0
        arpu_ci  = _bootstrap_ci(w["revenue"].values) if n_w > 1 else (arpu, arpu)
        return {"pct": pct, "pct_ci": (ci_lo * 100, ci_hi * 100),
                "arpu": arpu, "arpu_ci": arpu_ci, "n": n_w, "n_payers": n_payers}

    sc = whale_stats(ab[ab["split_group"] == 0])
    st = whale_stats(ab[ab["split_group"] == 1])

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle(
        f"Whale Segment Analysis  (cutoff ≥ ${cutoff:,.0f} — top 25% of revenue)\n"
        "Directional only — small n per group, treat as exploratory",
        fontsize=12, y=1.02,
    )

    # Left: whale share of payers
    vals_pct = [sc["pct"], st["pct"]]
    pct_cis  = [sc["pct_ci"], st["pct_ci"]]
    bars0 = axes[0].bar(["Control", "Test"], vals_pct,
                        color=[CTRL_COLOR, TEST_COLOR], width=0.45, zorder=3)
    axes[0].errorbar(
        [0, 1], vals_pct,
        yerr=[[v - ci[0] for v, ci in zip(vals_pct, pct_cis)],
              [ci[1] - v for v, ci in zip(vals_pct, pct_cis)]],
        fmt="none", color="#222", capsize=6, linewidth=1.6, zorder=4,
    )
    for bar, val, ci in zip(bars0, vals_pct, pct_cis):
        axes[0].text(bar.get_x() + bar.get_width() / 2, ci[1] + max(vals_pct) * 0.04,
                     f"{val:.1f}%", ha="center", va="bottom", fontsize=13, fontweight="bold")
    axes[0].set_title(
        f"Whale Share of Payers\n(ctrl: {sc['n']}/{sc['n_payers']} payers, "
        f"test: {st['n']}/{st['n_payers']} payers)",
        fontsize=11,
    )
    axes[0].set_ylabel("Whale % of Payers", fontsize=11)
    axes[0].set_ylim(0, max(ci[1] for ci in pct_cis) * 1.5)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))

    # Right: whale average revenue with bootstrap CI
    vals_arpu = [sc["arpu"], st["arpu"]]
    arpu_cis  = [sc["arpu_ci"], st["arpu_ci"]]
    bars1 = axes[1].bar(["Control", "Test"], vals_arpu,
                        color=[CTRL_COLOR, TEST_COLOR], width=0.45, zorder=3)
    axes[1].errorbar(
        [0, 1], vals_arpu,
        yerr=[[v - ci[0] for v, ci in zip(vals_arpu, arpu_cis)],
              [ci[1] - v for v, ci in zip(vals_arpu, arpu_cis)]],
        fmt="none", color="#222", capsize=6, linewidth=1.6, zorder=4,
    )
    rel = (vals_arpu[1] / vals_arpu[0] - 1) * 100 if vals_arpu[0] else 0
    for bar, val, ci in zip(bars1, vals_arpu, arpu_cis):
        axes[1].text(bar.get_x() + bar.get_width() / 2, ci[1] + max(vals_arpu) * 0.03,
                     f"${val:,.0f}", ha="center", va="bottom", fontsize=13, fontweight="bold")
    axes[1].set_title(f"Avg Revenue per Whale\nObserved lift: {rel:+.1f}%  (95% bootstrap CI)", fontsize=11)
    axes[1].set_ylabel("Whale Avg Revenue (USD)", fontsize=11)
    axes[1].set_ylim(0, max(ci[1] for ci in arpu_cis) * 1.35)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    fig.tight_layout()
    save(fig, "06_whale_analysis.png")


# ── Chart 07: Sanity Checks — 2×2 grid ───────────────────────────────────────

def chart07_sanity_combined(ab):
    dims = [d for d in ["gender", "age_group", "country_group", "id_traffic_source"]
            if d in ab.columns and ab[d].nunique() > 1]
    if not dims:
        print("  SKIP chart07: no multi-level attribute columns found")
        return

    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle(
        "Sanity Checks: Group Balance on Invariant Metrics\n"
        "Overlapping confidence intervals = no significant imbalance",
        fontsize=14, y=1.01,
    )
    axes_flat = axes.flatten()

    for ax, dim in zip(axes_flat, dims):
        raw    = pd.crosstab(ab[dim], ab["split_group"])
        raw.columns = raw.columns.astype(int)
        ct_pct = raw.div(raw.sum(axis=0)) * 100
        ct_pct = ct_pct.sort_values(0, ascending=True)
        raw    = raw.loc[ct_pct.index]

        x = np.arange(len(ct_pct))
        w = 0.35

        for i, cat in enumerate(ct_pct.index):
            for offset, grp_col, color, label in [
                (w / 2,  0, CTRL_COLOR, f"Control (n={n_c:,})"),
                (-w / 2, 1, TEST_COLOR,  f"Test (n={n_t:,})"),
            ]:
                count = raw.loc[cat, grp_col]
                total = n_c if grp_col == 0 else n_t
                pct   = count / total * 100
                ci_lo, ci_hi = _prop_ci(count, total)
                ax.barh(i + offset, pct, w, color=color, alpha=0.85,
                        label=label if i == 0 else "_", zorder=3)
                ax.errorbar(pct, i + offset,
                            xerr=[[(pct - ci_lo * 100)], [(ci_hi * 100 - pct)]],
                            fmt="none", color="#222", capsize=3, linewidth=1.2, zorder=4)

        ax.set_yticks(x)
        ax.set_yticklabels(ct_pct.index.astype(str), fontsize=9)
        ax.set_xlabel("% of group", fontsize=10, labelpad=6)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.set_title(dim.replace("_", " ").title(), fontsize=12, pad=8)
        ax.legend(fontsize=8.5, loc="lower right", framealpha=0.9)
        ax.grid(axis="x", alpha=0.35, linestyle="--")
        ax.grid(axis="y", visible=False)

    for ax in axes_flat[len(dims):]:
        ax.set_visible(False)

    fig.tight_layout()
    save(fig, "07_sanity_combined.png")


# ── Chart 07b: OS Distribution — imbalance sanity check ─────────────────────

def chart07b_os_distribution(ab):
    col = "system"
    if col not in ab.columns or ab[col].nunique() < 2:
        print("  SKIP chart07b: 'system' column missing or single-valued")
        return

    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())

    raw = pd.crosstab(ab[col], ab["split_group"])
    raw.columns = raw.columns.astype(int)
    ct_pct = raw.div(raw.sum(axis=0)) * 100
    ct_pct = ct_pct.sort_values(0, ascending=True)
    raw = raw.loc[ct_pct.index]

    from scipy.stats import chi2_contingency
    chi2, p_chi2, _, _ = chi2_contingency(raw)

    fig, ax = plt.subplots(figsize=(10, max(4, len(ct_pct) * 0.65 + 2)))
    x = np.arange(len(ct_pct))
    w = 0.35

    for i, cat in enumerate(ct_pct.index):
        for offset, grp_col, color, label in [
            (w / 2,  0, CTRL_COLOR, f"Control (n={n_c:,})"),
            (-w / 2, 1, TEST_COLOR,  f"Test (n={n_t:,})"),
        ]:
            count = raw.loc[cat, grp_col] if grp_col in raw.columns else 0
            total = n_c if grp_col == 0 else n_t
            pct   = count / total * 100
            ci_lo, ci_hi = _prop_ci(count, total)
            ax.barh(i + offset, pct, w, color=color, alpha=0.85,
                    label=label if i == 0 else "_", zorder=3)
            ax.errorbar(pct, i + offset,
                        xerr=[[(pct - ci_lo * 100)], [(ci_hi * 100 - pct)]],
                        fmt="none", color="#222", capsize=3, linewidth=1.2, zorder=4)

    ax.set_yticks(x)
    ax.set_yticklabels(ct_pct.index.astype(str), fontsize=10)
    ax.set_xlabel("% of group", fontsize=11, labelpad=6)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_title(
        f"OS Distribution by A/B Group — Sanity Check\n"
        f"chi² = {chi2:.2f}, p = {p_chi2:.4f}  "
        f"({'IMBALANCED' if p_chi2 < 0.05 else 'Balanced'})",
        fontsize=12, pad=10,
    )
    ax.legend(fontsize=10, loc="lower right", framealpha=0.9)
    ax.grid(axis="x", alpha=0.35, linestyle="--")
    ax.grid(axis="y", visible=False)

    fig.subplots_adjust(bottom=0.15)
    fig.text(
        0.5, 0.03,
        "Error bars = 95% Wilson CI.  "
        "Non-overlapping bars for iOS/Android confirm statistically significant OS imbalance between groups.",
        ha="center", fontsize=8.5, color=ANNOTATION_COLOR, style="italic",
    )
    save(fig, "07b_os_distribution.png")


def main():
    _setup_style()
    print("=== Step 8: Generating Charts ===")
    df = load_mobile_payments()
    ab = _ab_with_attrs(df)

    chart01_primary_metrics(ab)
    chart02_03_amount_trend(ab, df)
    chart05_country_heatmap(ab)
    chart06_whale_analysis(ab)
    chart07_sanity_combined(ab)
    chart07b_os_distribution(ab)
    print(f"\nDone. All charts saved to: {CHARTS_DIR}")


if __name__ == "__main__":
    main()
