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

from constants import SCRIPT_DIR, TEST_START, PAYMENT_START, build_ab_user_revenue, load_mobile_payments

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


def _bootstrap_sum_ci(values, n_boot=5_000, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)
    boots = rng.choice(values, (n_boot, len(values)), replace=True).sum(1)
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


_GENDER_ORDER   = ["male", "female"]
_AGE_ORDER      = ["5", "4", "3", "2", "1"]          # barh bottom→top, so list is reversed display order
_TRAFFIC_ORDER  = ["corellia", "jakku", "mandalore", "coruscant", "alderaan"]
_SYSTEM_ORDER   = ["mac", "other", "android", "ios"]
_COUNTRY_ORDER  = ["4", "3", "2", "1"]

_DIM_ORDER = {
    "gender":            _GENDER_ORDER,
    "age_group":         _AGE_ORDER,
    "id_traffic_source": _TRAFFIC_ORDER,
    "system":            _SYSTEM_ORDER,
    "country_group":     _COUNTRY_ORDER,
}


def _canonical_cats(cats, dim):
    """Return categories in stable canonical order."""
    order = _DIM_ORDER.get(dim)
    if order is None:
        return sorted(cats)
    lower_map = {str(c).lower(): c for c in cats}
    ordered = [lower_map[k] for k in order if k in lower_map]
    rest = sorted(c for c in cats if str(c).lower() not in order)
    return ordered + rest


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


# ── Chart 01: Primary Metrics — PPU + ARPU + ARPPU + Total Revenue ───────────

def chart01_primary_metrics(ab):
    rng = np.random.default_rng(42)
    ctrl = ab[ab["split_group"] == 0]
    test = ab[ab["split_group"] == 1]
    ctrl_payers = ctrl.loc[ctrl["revenue"] > 0, "revenue"]
    test_payers = test.loc[test["revenue"] > 0, "revenue"]

    _, p_ppu  = stats.mannwhitneyu(test["payment_count"], ctrl["payment_count"], alternative="greater")
    _, p_arpu = stats.mannwhitneyu(test["revenue"], ctrl["revenue"], alternative="greater")
    _, p_arpp = stats.mannwhitneyu(test_payers, ctrl_payers, alternative="greater")

    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    fig.suptitle("Primary Metrics: Test vs Control — Mobile A/B Test", fontsize=13, y=1.01)

    _bar_panel(axes[0, 0], ctrl["payment_count"], test["payment_count"],
               "Avg Payments Per User",
               f"Payments Per User (PPU) [PRIMARY]\np = {p_ppu:.3f}",
               val_fmt="{:.4f}", rng=rng)

    _bar_panel(axes[0, 1], ctrl["revenue"], test["revenue"],
               "Avg Revenue Per User (USD)",
               f"ARPU (Avg Revenue Per User)\np = {p_arpu:.3f}",
               val_fmt="${:.2f}", rng=rng)
    axes[0, 1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))

    _bar_panel(axes[1, 0], ctrl_payers, test_payers,
               "Avg Revenue Per Paying User (USD)",
               f"ARPPU (Avg Revenue Per Paying User)\np = {p_arpp:.3f}",
               val_fmt="${:.2f}", rng=rng)
    axes[1, 0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))

    total_c = float(ctrl["revenue"].sum())
    total_t = float(test["revenue"].sum())
    ci_total_c = _bootstrap_sum_ci(ctrl["revenue"].values, rng=rng)
    ci_total_t = _bootstrap_sum_ci(test["revenue"].values, rng=rng)
    total_vals = [total_c, total_t]
    total_cis  = [ci_total_c, ci_total_t]
    bars = axes[1, 1].bar(
        [f"Control\nn={len(ctrl):,}", f"Test\nn={len(test):,}"],
        total_vals, color=[CTRL_COLOR, TEST_COLOR], width=0.45, zorder=3,
    )
    axes[1, 1].errorbar(
        [0, 1], total_vals,
        yerr=[[v - ci[0] for v, ci in zip(total_vals, total_cis)],
              [ci[1] - v for v, ci in zip(total_vals, total_cis)]],
        fmt="none", color="#222", capsize=7, linewidth=1.8, zorder=4,
    )
    for bar, val, ci in zip(bars, total_vals, total_cis):
        axes[1, 1].text(
            bar.get_x() + bar.get_width() / 2,
            ci[1] + max(total_vals) * 0.04,
            f"${val:,.0f}", ha="center", va="bottom", fontsize=13, fontweight="bold",
        )
    axes[1, 1].set_ylabel("Total Revenue (USD)", fontsize=11)
    axes[1, 1].set_title(f"Total Revenue\np = {p_arpu:.3f} (same test as ARPU)", fontsize=11, pad=10)
    axes[1, 1].set_ylim(0, max(ci[1] for ci in total_cis) * 1.3)
    axes[1, 1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.06)
    fig.text(
        0.5, 0.01,
        "Error bars = 95% bootstrap CI.  PPU & ARPU: all users.  ARPPU: payers only.",
        ha="center", fontsize=8.5, color=ANNOTATION_COLOR, style="italic",
    )
    save(fig, "01_primary_metrics.png")


# ── Chart 02a: Cumulative Revenue Curve (single panel) ───────────────────────

def _lorenz_data(revenues):
    """Cumulative % of revenue vs % of payers (sorted desc by revenue)."""
    sorted_rev = np.sort(revenues)[::-1]
    cumrev = np.cumsum(sorted_rev)
    n = len(sorted_rev)
    pct_payers = np.linspace(0, 100, n + 1)
    pct_revenue = np.concatenate([[0], cumrev / cumrev[-1] * 100])
    return pct_payers, pct_revenue


def chart02_cumulative(ab):
    ctrl_payers = ab[(ab["split_group"] == 0) & (ab["revenue"] > 0)]["revenue"].values
    test_payers = ab[(ab["split_group"] == 1) & (ab["revenue"] > 0)]["revenue"].values

    fig, ax = plt.subplots(figsize=(8, 7))

    px_c, py_c = _lorenz_data(ctrl_payers)
    px_t, py_t = _lorenz_data(test_payers)

    ax.plot(px_c, py_c, color=CTRL_COLOR, linewidth=2.5,
            label=f"Control ({len(ctrl_payers):,} payers)")
    ax.plot(px_t, py_t, color=TEST_COLOR, linewidth=2.5,
            label=f"Test ({len(test_payers):,} payers)")
    ax.axline((0, 0), (100, 100), color="#bbb", linestyle="--", linewidth=1,
              label="Perfect equality")

    # 75% revenue marker — show what % of payers generates 75% of revenue
    x_75_c = float(np.interp(75.0, py_c[1:], px_c[1:]))
    x_75_t = float(np.interp(75.0, py_t[1:], px_t[1:]))
    ax.axhline(75, color="#888", linestyle=":", linewidth=1.2, alpha=0.7)
    ax.axvline(x_75_c, color=CTRL_COLOR, linestyle=":", linewidth=1.5, alpha=0.8)
    ax.axvline(x_75_t, color=TEST_COLOR, linestyle=":", linewidth=1.5, alpha=0.8)
    ax.annotate(
        f"75% of revenue:\nCtrl — top {x_75_c:.0f}% of payers\nTest — top {x_75_t:.0f}% of payers",
        xy=(max(x_75_c, x_75_t), 75),
        xytext=(min(x_75_c, x_75_t) + 10, 54),
        fontsize=9.5, color=ANNOTATION_COLOR,
        arrowprops=dict(arrowstyle="->", color="#aaa", lw=0.9),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.85),
    )

    ax.set_xlabel("Top X% of Payers (ranked by revenue, high→low)", fontsize=11)
    ax.set_ylabel("Cumulative % of Total Revenue", fontsize=11)
    ax.set_title("Revenue Concentration — Whale Model\n(top payers dominate)", fontsize=12, pad=10)
    ax.legend(fontsize=10, framealpha=0.9)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(axis="both", alpha=0.3, linestyle="--")

    fig.tight_layout()
    save(fig, "02_cumulative_revenue.png")


# ── Chart 02b: Daily Payment Count + Daily Revenue ───────────────────────────

def chart02_daily_trend(ab, df):
    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())
    ab_ids = set(ab["id_user"])

    post = df[
        df["id_user"].isin(ab_ids)
        & df["date_payment"].notna()
        & (df["date_payment"] >= PAYMENT_START)
        & (df["successful_payment"] == 1)
    ].copy()
    post["date"] = post["date_payment"].dt.date

    daily_pay = post.groupby(["date", "split_group"]).size().unstack(fill_value=0)
    daily_pay.columns = daily_pay.columns.astype(int)
    for col in [0, 1]:
        if col not in daily_pay.columns:
            daily_pay[col] = 0

    daily_rev = post.groupby(["date", "split_group"])["amount"].sum().unstack(fill_value=0)
    daily_rev.columns = daily_rev.columns.astype(int)
    for col in [0, 1]:
        if col not in daily_rev.columns:
            daily_rev[col] = 0

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Daily Payment Count & Daily Revenue by Group", fontsize=13, y=1.02)

    for ax, data, ylabel, title, fmt in [
        (axes[0], daily_pay, "Successful Payments per Day",
         "Daily Payment Count\n(July 24 – end of experiment)", None),
        (axes[1], daily_rev, "Daily Revenue (USD)",
         "Daily Revenue\n(July 24 – end of experiment)",
         mticker.FuncFormatter(lambda v, _: f"${v:,.0f}")),
    ]:
        ax.plot(data.index, data[0], color=CTRL_COLOR,
                label=f"Control (n={n_c:,})", linewidth=2, zorder=3)
        ax.plot(data.index, data[1], color=TEST_COLOR,
                label=f"Test (n={n_t:,})", linewidth=2, zorder=3)
        ax.fill_between(data.index, data[0], data[1], alpha=0.08, color="#888")
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=11, pad=10)
        ax.legend(fontsize=10, framealpha=0.9)
        ax.grid(axis="y", alpha=0.35, linestyle="--")
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="x", rotation=30)
        if fmt:
            ax.yaxis.set_major_formatter(fmt)

    fig.tight_layout()
    save(fig, "02_daily_trend.png")


# ── Chart 05: PPU by Segment — 2+2+1 layout (age_group full-width at bottom) ─

def chart05_segment_ppu(ab):
    from matplotlib.gridspec import GridSpec

    # age_group at bottom (biggest observed difference); others in 2×2
    preferred_order = ["gender", "country_group", "id_traffic_source", "system", "age_group"]
    dims = [d for d in preferred_order if d in ab.columns and ab[d].nunique() > 1]
    if not dims:
        print("  SKIP chart05: no segmentation columns found")
        return

    bottom_dim = "age_group" if "age_group" in dims else dims[-1]
    top_dims = [d for d in dims if d != bottom_dim][:4]
    plot_dims = top_dims + [bottom_dim]

    n_top_rows = (len(top_dims) + 1) // 2
    fig = plt.figure(figsize=(20, 7 * n_top_rows + 9))
    gs = GridSpec(n_top_rows + 1, 2, figure=fig, hspace=0.5, wspace=0.35)
    fig.suptitle(
        "Payments Per User (PPU) by Segment: Test vs Control\n"
        "Error bars = 95% bootstrap CI (mean PPU)",
        fontsize=14, y=1.01,
    )

    axes_list = [fig.add_subplot(gs[i // 2, i % 2]) for i in range(len(top_dims))]
    axes_list.append(fig.add_subplot(gs[n_top_rows, :]))

    for ax, dim in zip(axes_list, plot_dims):
        categories = _canonical_cats(ab[dim].dropna().unique().tolist(), dim)
        rng_loc = np.random.default_rng(42)

        x = np.arange(len(categories))
        w = 0.35
        legend_added = {0: False, 1: False}
        for i, cat in enumerate(categories):
            for offset, grp, color, label in [
                (w / 2,  0, CTRL_COLOR, "Control"),
                (-w / 2, 1, TEST_COLOR, "Test"),
            ]:
                vals = ab.loc[
                    (ab[dim] == cat) & (ab["split_group"] == grp), "payment_count"
                ].values
                if len(vals) == 0:
                    continue
                mean_val = float(vals.mean())
                bar_label = label if not legend_added[grp] else "_"
                legend_added[grp] = True
                ax.barh(i + offset, mean_val, w, color=color, alpha=0.88,
                        label=bar_label, zorder=3)
                if len(vals) >= 2:
                    ci_lo, ci_hi = _bootstrap_ci(vals, rng=rng_loc)
                    ax.errorbar(mean_val, i + offset,
                                xerr=[[mean_val - ci_lo], [ci_hi - mean_val]],
                                fmt="none", color="#222", capsize=3, linewidth=1.2, zorder=4)

        ax.set_yticks(x)
        ax.set_yticklabels([str(c) for c in categories], fontsize=9)
        ax.set_xlabel("Payments Per User (PPU)", fontsize=10, labelpad=6)
        is_bottom = (dim == bottom_dim)
        ax.set_title(dim.replace("_", " ").title(),
                     fontsize=14 if is_bottom else 12, pad=8,
                     fontweight="bold" if is_bottom else "normal")
        ax.legend(fontsize=8.5, loc="lower right", framealpha=0.9)
        ax.grid(axis="x", alpha=0.35, linestyle="--")
        ax.grid(axis="y", visible=False)

    save(fig, "05_segment_ppu.png")


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


# ── Chart 07: Sanity Checks — 2+2+1 layout (country_group full-width at bottom)

def chart07_sanity_combined(ab):
    from matplotlib.gridspec import GridSpec

    # country_group at bottom (shows the notable imbalance); others in 2×2
    preferred_order = ["gender", "age_group", "id_traffic_source", "system", "country_group"]
    dims = [d for d in preferred_order if d in ab.columns and ab[d].nunique() > 1]
    if not dims:
        print("  SKIP chart07: no multi-level attribute columns found")
        return

    n_c = int((ab["split_group"] == 0).sum())
    n_t = int((ab["split_group"] == 1).sum())

    bottom_dim = "country_group" if "country_group" in dims else dims[-1]
    top_dims = [d for d in dims if d != bottom_dim][:4]
    plot_dims = top_dims + [bottom_dim]

    n_top_rows = (len(top_dims) + 1) // 2
    fig = plt.figure(figsize=(20, 7 * n_top_rows + 9))
    gs = GridSpec(n_top_rows + 1, 2, figure=fig, hspace=0.45, wspace=0.3)
    fig.suptitle(
        "Sanity Checks: Group Balance on Invariant Metrics\n"
        "Overlapping confidence intervals = no significant imbalance",
        fontsize=14, y=1.01,
    )

    axes_list = [fig.add_subplot(gs[i // 2, i % 2]) for i in range(len(top_dims))]
    axes_list.append(fig.add_subplot(gs[n_top_rows, :]))

    for ax, dim in zip(axes_list, plot_dims):
        raw    = pd.crosstab(ab[dim], ab["split_group"])
        raw.columns = raw.columns.astype(int)
        ct_pct = raw.div(raw.sum(axis=0)) * 100
        cats_ordered = _canonical_cats(ct_pct.index.tolist(), dim)
        ct_pct = ct_pct.loc[cats_ordered]
        raw    = raw.loc[cats_ordered]

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
        ax.set_yticklabels(ct_pct.index.astype(str), fontsize=9)
        ax.set_xlabel("% of group", fontsize=10, labelpad=6)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        is_bottom = (dim == bottom_dim)
        ax.set_title(dim.replace("_", " ").title(),
                     fontsize=14 if is_bottom else 12, pad=8,
                     fontweight="bold" if is_bottom else "normal")
        ax.legend(fontsize=8.5, loc="lower right", framealpha=0.9)
        ax.grid(axis="x", alpha=0.35, linestyle="--")
        ax.grid(axis="y", visible=False)

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
    chart02_cumulative(ab)
    chart02_daily_trend(ab, df)
    chart05_segment_ppu(ab)
    chart06_whale_analysis(ab)
    chart07_sanity_combined(ab)
    print(f"\nDone. All charts saved to: {CHARTS_DIR}")


if __name__ == "__main__":
    main()
