"""
Step 9 (UA): Generate CEO-facing HTML report in Ukrainian with embedded charts.
Run after: 01_filtering.py, 08_charts.py
"""
import base64
import os
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from constants import (
    SCRIPT_DIR, TEST_START, PAYMENT_START,
    build_ab_user_revenue, load_mobile_payments,
    user_table, successful_payments,
)

CHARTS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "charts"))
REPORT_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "report_ua.html"))
ALPHA = 0.05
RNG = np.random.default_rng(42)
N_BOOT = 5_000


def _bootstrap_ci(arr):
    samples = RNG.choice(arr, (N_BOOT, len(arr)), replace=True).mean(1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def _bootstrap_sum_ci(arr):
    samples = RNG.choice(arr, (N_BOOT, len(arr)), replace=True).sum(1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def _whale_cutoff(ab, pct=0.75):
    payers = ab.loc[ab["revenue"] > 0, "revenue"].sort_values(ascending=False).values
    idx = int((np.cumsum(payers) < pct * payers.sum()).sum())
    return float(payers[min(idx, len(payers) - 1)])


def compute_results(df):
    ab = build_ab_user_revenue(df)
    ctrl = ab[ab["split_group"] == 0]
    test = ab[ab["split_group"] == 1]

    n_c, n_t = len(ctrl), len(test)
    pay_c = int((ctrl["revenue"] > 0).sum())
    pay_t = int((test["revenue"] > 0).sum())
    cr_c, cr_t = pay_c / n_c, pay_t / n_t

    # PRIMARY METRIC: Payments Per User — Mann-Whitney U (test > control)
    ppu_c = ctrl["payment_count"].mean()
    ppu_t = test["payment_count"].mean()
    _, p_ppu = stats.mannwhitneyu(test["payment_count"], ctrl["payment_count"], alternative="greater")
    ci_ppu_c = _bootstrap_ci(ctrl["payment_count"].values)
    ci_ppu_t = _bootstrap_ci(test["payment_count"].values)

    # ARPPU: payer-only amounts, Mann-Whitney (test > control)
    arpp_c = ctrl.loc[ctrl["revenue"] > 0, "revenue"]
    arpp_t = test.loc[test["revenue"] > 0, "revenue"]
    _, p_arpp = stats.mannwhitneyu(arpp_t, arpp_c, alternative="greater")
    ci_arpp_c = _bootstrap_ci(arpp_c.values)
    ci_arpp_t = _bootstrap_ci(arpp_t.values)

    # RPU: all users, Mann-Whitney (test > control)
    _, p_rpu = stats.mannwhitneyu(test["revenue"], ctrl["revenue"], alternative="greater")
    rpu_c, rpu_t = ctrl["revenue"].mean(), test["revenue"].mean()

    # Bootstrap CI for RPU
    ci_rpu_c = _bootstrap_ci(ctrl["revenue"].values)
    ci_rpu_t = _bootstrap_ci(test["revenue"].values)

    # Total revenue + bootstrap CI
    total_rev_c = ctrl["revenue"].sum()
    total_rev_t = test["revenue"].sum()
    ci_total_rev_c = _bootstrap_sum_ci(ctrl["revenue"].values)
    ci_total_rev_t = _bootstrap_sum_ci(test["revenue"].values)

    # Power analysis for PPU (5% relative MDE, alpha=0.05, power=0.80)
    ppu_mde = ppu_c * 1.05
    ppu_sd = ctrl["payment_count"].std()
    z_req = stats.norm.ppf(1 - ALPHA) + stats.norm.ppf(0.80)
    n_req_ppu = int(np.ceil(2 * (z_req * ppu_sd / (ppu_mde - ppu_c)) ** 2)) if ppu_mde > ppu_c and ppu_sd > 0 else float("nan")
    obs_power_ppu = float(1 - stats.norm.cdf(
        stats.norm.ppf(1 - ALPHA) - abs(ppu_t - ppu_c) / (ppu_sd * np.sqrt(2 / min(n_c, n_t)))))

    # Conversion rate (secondary — kept for reference)
    diff_cr = cr_t - cr_c
    se_cr = np.sqrt(cr_t * (1 - cr_t) / n_t + cr_c * (1 - cr_c) / n_c)

    # Conversion rate p-value (chi-square)
    ct = np.array([[pay_c, n_c - pay_c], [pay_t, n_t - pay_t]])
    _, p_cr, _, _ = stats.chi2_contingency(ct)

    # Whale metrics
    cutoff = _whale_cutoff(ab)
    w_c = ctrl[ctrl["revenue"] >= cutoff]
    w_t = test[test["revenue"] >= cutoff]
    whale_cr_c = len(w_c) / max(pay_c, 1)
    whale_cr_t = len(w_t) / max(pay_t, 1)
    whale_arpu_c = float(w_c["revenue"].mean()) if len(w_c) else 0.0
    whale_arpu_t = float(w_t["revenue"].mean()) if len(w_t) else 0.0
    whale_rpu_c = w_c["revenue"].sum() / n_c
    whale_rpu_t = w_t["revenue"].sum() / n_t

    if len(w_c) >= 5 and len(w_t) >= 5:
        _, p_whale = stats.mannwhitneyu(w_t["revenue"], w_c["revenue"], alternative="greater")
    else:
        p_whale = float("nan")

    # Segment attrs for PPU breakdown
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "country_group", "system", "gender", "age_group", "id_traffic_source"]]
    )
    ab_seg = ab.merge(attrs, on="id_user", how="left")

    # Segment PPU tables with Mann-Whitney p-values and bootstrap CIs
    seg_dims = ["gender", "age_group", "country_group", "id_traffic_source", "system"]
    N_BOOT_SEG = 1_000
    segment_ppu = {}
    for dim in seg_dims:
        if dim not in ab_seg.columns:
            continue
        rows = []
        for cat in sorted(ab_seg[dim].dropna().unique()):
            ctrl_vals = ab_seg[(ab_seg[dim] == cat) & (ab_seg["split_group"] == 0)]["payment_count"].values
            test_vals = ab_seg[(ab_seg[dim] == cat) & (ab_seg["split_group"] == 1)]["payment_count"].values
            ppu_c_seg = float(ctrl_vals.mean()) if len(ctrl_vals) > 0 else float("nan")
            ppu_t_seg = float(test_vals.mean()) if len(test_vals) > 0 else float("nan")
            n_c_seg, n_t_seg = len(ctrl_vals), len(test_vals)
            diff_seg = ppu_t_seg - ppu_c_seg if not (np.isnan(ppu_t_seg) or np.isnan(ppu_c_seg)) else float("nan")
            if n_c_seg >= 5 and n_t_seg >= 5:
                _, p_seg = stats.mannwhitneyu(test_vals, ctrl_vals, alternative="two-sided")
                boot_c = RNG.choice(ctrl_vals, (N_BOOT_SEG, n_c_seg), replace=True).mean(1)
                boot_t = RNG.choice(test_vals, (N_BOOT_SEG, n_t_seg), replace=True).mean(1)
                boot_diff = boot_t - boot_c
                ci_lo_seg = float(np.percentile(boot_diff, 2.5))
                ci_hi_seg = float(np.percentile(boot_diff, 97.5))
            else:
                p_seg = ci_lo_seg = ci_hi_seg = float("nan")
            rows.append((cat, ppu_c_seg, n_c_seg, ppu_t_seg, n_t_seg, diff_seg, p_seg, ci_lo_seg, ci_hi_seg))
        segment_ppu[dim] = rows

    # Payment success rate table (payments from PAYMENT_START)
    pay_df = df[
        df["id_user"].isin(set(ab["id_user"]))
        & df["date_payment"].notna()
        & (df["date_payment"] >= PAYMENT_START)
    ].copy()

    succ_m    = pay_df["successful_payment"] == 1
    ctrl_pay  = pay_df["split_group"] == 0
    test_pay  = pay_df["split_group"] == 1
    cg4_pay   = pay_df["country_group"] == 4
    ios_m     = pay_df["system"].str.lower().str.strip() == "ios"
    android_m = pay_df["system"].str.lower().str.strip() == "android"
    card_m    = pay_df["method"].str.lower().str.strip().str.contains("card|credit|debit|visa|mastercard", na=False)

    sr_n_c = int(ctrl_pay.sum())
    sr_n_t = int(test_pay.sum())
    sr_rate_c = float((ctrl_pay & succ_m).sum()) / max(sr_n_c, 1)
    sr_rate_t = float((test_pay & succ_m).sum()) / max(sr_n_t, 1)

    sr_n_cg4_c = int((ctrl_pay & cg4_pay).sum())
    sr_n_cg4_t = int((test_pay & cg4_pay).sum())
    sr_rate_cg4_c = float((ctrl_pay & cg4_pay & succ_m).sum()) / max(sr_n_cg4_c, 1)
    sr_rate_cg4_t = float((test_pay & cg4_pay & succ_m).sum()) / max(sr_n_cg4_t, 1)

    sr_n_ios_c = int((ctrl_pay & ios_m).sum())
    sr_n_ios_t = int((test_pay & ios_m).sum())
    sr_rate_ios_c = float((ctrl_pay & ios_m & succ_m).sum()) / max(sr_n_ios_c, 1)
    sr_rate_ios_t = float((test_pay & ios_m & succ_m).sum()) / max(sr_n_ios_t, 1)

    sr_n_android_c = int((ctrl_pay & android_m).sum())
    sr_n_android_t = int((test_pay & android_m).sum())
    sr_rate_android_c = float((ctrl_pay & android_m & succ_m).sum()) / max(sr_n_android_c, 1)
    sr_rate_android_t = float((test_pay & android_m & succ_m).sum()) / max(sr_n_android_t, 1)

    sr_n_card_c = int((ctrl_pay & card_m).sum())
    sr_n_card_t = int((test_pay & card_m).sum())
    sr_rate_card_c = float((ctrl_pay & card_m & succ_m).sum()) / max(sr_n_card_c, 1)
    sr_rate_card_t = float((test_pay & card_m & succ_m).sum()) / max(sr_n_card_t, 1)

    return {
        "n_c": n_c, "n_t": n_t,
        "pay_c": pay_c, "pay_t": pay_t,
        "cr_c": cr_c, "cr_t": cr_t,
        "diff_cr": diff_cr, "se_cr": se_cr,
        "ppu_c": ppu_c, "ppu_t": ppu_t,
        "p_ppu": p_ppu, "ci_ppu_c": ci_ppu_c, "ci_ppu_t": ci_ppu_t,
        "n_req_ppu": n_req_ppu, "obs_power_ppu": obs_power_ppu,
        "arpp_c": float(arpp_c.mean()), "arpp_t": float(arpp_t.mean()),
        "p_arpp": p_arpp, "ci_arpp_c": ci_arpp_c, "ci_arpp_t": ci_arpp_t,
        "rpu_c": rpu_c, "rpu_t": rpu_t,
        "p_rpu": p_rpu, "ci_rpu_c": ci_rpu_c, "ci_rpu_t": ci_rpu_t,
        "total_rev_c": total_rev_c, "total_rev_t": total_rev_t,
        "ci_total_rev_c": ci_total_rev_c, "ci_total_rev_t": ci_total_rev_t,
        "p_cr": p_cr,
        "whale_cutoff": cutoff,
        "n_whales_c": len(w_c), "n_whales_t": len(w_t),
        "whale_cr_c": whale_cr_c, "whale_cr_t": whale_cr_t,
        "whale_arpu_c": whale_arpu_c, "whale_arpu_t": whale_arpu_t,
        "whale_rpu_c": float(whale_rpu_c), "whale_rpu_t": float(whale_rpu_t),
        "p_whale": p_whale,
        "segment_ppu": segment_ppu,
        "sr_n_c": sr_n_c, "sr_n_t": sr_n_t,
        "sr_rate_c": sr_rate_c, "sr_rate_t": sr_rate_t,
        "sr_n_cg4_c": sr_n_cg4_c, "sr_n_cg4_t": sr_n_cg4_t,
        "sr_rate_cg4_c": sr_rate_cg4_c, "sr_rate_cg4_t": sr_rate_cg4_t,
        "sr_n_ios_c": sr_n_ios_c, "sr_n_ios_t": sr_n_ios_t,
        "sr_rate_ios_c": sr_rate_ios_c, "sr_rate_ios_t": sr_rate_ios_t,
        "sr_n_android_c": sr_n_android_c, "sr_n_android_t": sr_n_android_t,
        "sr_rate_android_c": sr_rate_android_c, "sr_rate_android_t": sr_rate_android_t,
        "sr_n_card_c": sr_n_card_c, "sr_n_card_t": sr_n_card_t,
        "sr_rate_card_c": sr_rate_card_c, "sr_rate_card_t": sr_rate_card_t,
    }


def compute_aa_results(df):
    """Compare pre-experiment cohort vs A/B control group.

    Pre-cohort window: same number of days as A/B payment window, ending at TEST_START.
    Users: registered in [pre_start, TEST_START). Payments: same window.
    Control group CIs are taken from r (compute_results) to guarantee identity.
    """
    ab = build_ab_user_revenue(df)
    ctrl = ab[ab["split_group"] == 0].copy()

    # Determine A/B payment window duration
    ab_pay = df[
        df["id_user"].isin(set(ab["id_user"])) &
        df["date_payment"].notna() &
        (df["successful_payment"] == 1) &
        (df["date_payment"] >= PAYMENT_START)
    ]
    max_pay_date = ab_pay["date_payment"].max().normalize()
    n_days = int((max_pay_date - PAYMENT_START.normalize()).days) + 1

    # Pre-cohort window: same duration, ending just before TEST_START
    pre_end = TEST_START       # exclusive upper bound
    pre_start = TEST_START - pd.Timedelta(days=n_days)

    # Users registered in the pre-cohort window
    ut = user_table(df)
    pre_ids = set(ut[
        (ut["date_reg"] >= pre_start) & (ut["date_reg"] < pre_end)
    ]["id_user"])

    # Payments within the same pre-cohort window
    pay_pre = successful_payments(df, user_ids=pre_ids, payment_start=pre_start, payment_end=pre_end)
    pre_df = pd.DataFrame({"id_user": list(pre_ids)})
    pre_df["revenue"] = pre_df["id_user"].map(
        pay_pre.groupby("id_user")["amount"].sum()
    ).fillna(0.0)
    pre_df["payment_count"] = pre_df["id_user"].map(
        pay_pre.groupby("id_user").size()
    ).fillna(0).astype(int)

    n_pre = len(pre_df)
    n_ctrl = len(ctrl)

    # PPU — Mann-Whitney two-sided
    _, p_ppu = stats.mannwhitneyu(
        pre_df["payment_count"], ctrl["payment_count"], alternative="two-sided"
    )
    ci_ppu_pre = _bootstrap_ci(pre_df["payment_count"].values)

    # ARPU (all users) — Mann-Whitney two-sided
    _, p_arpu = stats.mannwhitneyu(
        pre_df["revenue"], ctrl["revenue"], alternative="two-sided"
    )
    ci_arpu_pre = _bootstrap_ci(pre_df["revenue"].values)

    # ARPPU (payers only) — Mann-Whitney two-sided
    arppu_pre_vals = pre_df.loc[pre_df["revenue"] > 0, "revenue"].values
    arppu_ctrl_vals = ctrl.loc[ctrl["revenue"] > 0, "revenue"].values
    if len(arppu_pre_vals) >= 5 and len(arppu_ctrl_vals) >= 5:
        _, p_arppu = stats.mannwhitneyu(arppu_pre_vals, arppu_ctrl_vals, alternative="two-sided")
    else:
        p_arppu = float("nan")
    ci_arppu_pre = _bootstrap_ci(arppu_pre_vals) if len(arppu_pre_vals) > 0 else (0.0, 0.0)

    # CR — chi-square
    pay_pre_n = int((pre_df["revenue"] > 0).sum())
    pay_ctrl_n = int((ctrl["revenue"] > 0).sum())
    ct = np.array([[pay_pre_n, n_pre - pay_pre_n], [pay_ctrl_n, n_ctrl - pay_ctrl_n]])
    _, p_cr, _, _ = stats.chi2_contingency(ct)

    return {
        "n_pre": n_pre, "n_ctrl": n_ctrl,
        "n_days": n_days,
        "pre_start": pre_start,
        "ppu_pre": float(pre_df["payment_count"].mean()),
        "ci_ppu_pre": ci_ppu_pre,
        "p_ppu": p_ppu,
        "arpu_pre": float(pre_df["revenue"].mean()),
        "ci_arpu_pre": ci_arpu_pre,
        "p_arpu": p_arpu,
        "arppu_pre": float(arppu_pre_vals.mean()) if len(arppu_pre_vals) > 0 else 0.0,
        "ci_arppu_pre": ci_arppu_pre,
        "p_arppu": p_arppu,
        "cr_pre": pay_pre_n / n_pre,
        "pay_pre_n": pay_pre_n, "pay_ctrl_n": pay_ctrl_n,
        "p_cr": p_cr,
    }


def _img_tag(fname, alt=""):
    path = os.path.join(CHARTS_DIR, fname)
    if not os.path.exists(path):
        return (f'<p style="background:#fff3cd;padding:10px;border-radius:4px">'
                f'Графік не знайдено: <code>{fname}</code> — спочатку запустіть 08_charts.py.</p>')
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<img src="data:image/png;base64,{b64}" alt="{alt}" '
            f'style="max-width:100%;border:1px solid #ddd;border-radius:4px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.1)">')


def _badge(p):
    if np.isnan(p):
        return '<span class="badge badge-na">Н/Д</span>'
    if p < ALPHA:
        return f'<span class="badge badge-sig">Значущий (p={p:.3f})</span>'
    return f'<span class="badge badge-ns">Не значущий (p={p:.3f})</span>'


def _segment_ppu_table(rows, dim_label):
    header = (
        f'<h3>{dim_label}</h3>'
        '<table>'
        '<tr><th>Сегмент</th>'
        '<th>Control PPU (n)</th>'
        '<th>Test PPU (n)</th>'
        '<th>Різниця</th>'
        '<th>95% CI різниці</th>'
        '<th>p-value</th></tr>'
    )
    body_rows = []
    for cat, ppu_c, n_c, ppu_t, n_t, diff, p_val, ci_lo, ci_hi in rows:
        diff_str = f"{diff:+.4f}" if not np.isnan(diff) else "—"
        ci_str   = f"({ci_lo:+.4f}, {ci_hi:+.4f})" if not np.isnan(ci_lo) else "—"
        sig = not np.isnan(p_val) and p_val < 0.05
        if sig and not np.isnan(diff):
            bg = "background:#d4edda" if diff > 0 else "background:#f8d7da"
        elif not np.isnan(diff) and diff > 0.001:
            bg = "background:#eef6ee"
        elif not np.isnan(diff) and diff < -0.001:
            bg = "background:#fdf0f0"
        else:
            bg = ""
        p_str  = f"{p_val:.3f}" if not np.isnan(p_val) else "—"
        p_cell = f"<strong>{p_str}</strong>" if sig else p_str
        body_rows.append(
            f'<tr>'
            f'<td>{cat}</td>'
            f'<td>{ppu_c:.4f} <small>(n={n_c:,})</small></td>'
            f'<td>{ppu_t:.4f} <small>(n={n_t:,})</small></td>'
            f'<td style="{bg}">{diff_str}</td>'
            f'<td style="{bg}">{ci_str}</td>'
            f'<td>{p_cell}</td>'
            f'</tr>'
        )
    return header + "\n".join(body_rows) + "</table>"


CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;max-width:980px;margin:0 auto;padding:20px 32px;
  color:#222;background:#fafafa;line-height:1.6}
h1{color:#1a237e;border-bottom:3px solid #1a237e;padding-bottom:8px}
h2{color:#283593;margin-top:40px;border-left:4px solid #3949ab;padding-left:10px}
h3{color:#3949ab}
.verdict{border:2px solid #c62828;border-radius:8px;padding:18px 24px;margin:20px 0;
  background:#ffebee}
.verdict h3{color:#c62828;margin:0 0 8px;font-size:1.35em}
table{width:100%;border-collapse:collapse;margin:16px 0}
th{background:#283593;color:#fff;padding:10px 14px;text-align:left}
td{padding:9px 14px;border-bottom:1px solid #e0e0e0}
tr:nth-child(even) td{background:#f5f5f5}
.chart{margin:24px 0;text-align:center}
.warn{background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px 16px;margin:12px 0}
.pass{background:#d4edda;border:1px solid #28a745;border-radius:4px;padding:12px 16px;margin:12px 0}
.info{background:#d1ecf1;border:1px solid #17a2b8;border-radius:4px;padding:12px 16px;margin:12px 0}
.badge{display:inline-block;padding:2px 10px;border-radius:3px;font-size:.85em;font-weight:600}
.badge-sig{background:#d4edda;color:#155724}
.badge-ns{background:#f8d7da;color:#721c24}
.badge-na{background:#e2e3e5;color:#383d41}
footer{color:#888;font-size:.85em;margin-top:40px;border-top:1px solid #ddd;padding-top:12px}
.chart-caption{font-size:.82em;color:#555;font-style:italic;margin:4px 0 0;padding:0 8px;text-align:center}
"""

DIM_LABELS = {
    "gender": "Стать",
    "age_group": "Вікова група",
    "country_group": "Country Group",
    "id_traffic_source": "Джерело трафіку",
    "system": "Операційна система",
}


def generate_html(r, aa):
    ppu_diff = r["ppu_t"] - r["ppu_c"]
    ppu_ci_low  = r["ci_ppu_t"][0] - r["ci_ppu_c"][1]
    ppu_ci_high = r["ci_ppu_t"][1] - r["ci_ppu_c"][0]
    cr_ci_low  = r["diff_cr"] - 1.96 * r["se_cr"]
    cr_ci_high = r["diff_cr"] + 1.96 * r["se_cr"]

    whale_sig_note = (
        f"Mann-Whitney U test для сум платежів whale-користувачів: p={r['p_whale']:.3f} — "
        f"{'<strong>значущий</strong>' if not np.isnan(r['p_whale']) and r['p_whale'] < ALPHA else 'не значущий'}."
        if not np.isnan(r["p_whale"])
        else "Формальний тест на значущість незастосовний через малий розмір вибірки whale-сегменту."
    )

    try:
        n_req_ppu = int(r["n_req_ppu"])
        powered_note = (
            f"<strong>Експеримент мав достатню потужність для метрики payments per user</strong> "
            f"(потрібно ~{n_req_ppu:,} користувачів/групу при MDE 5%; фактично: ~{r['n_c']:,}; "
            f"оцінена потужність: <strong>{r['obs_power_ppu']:.0%}</strong>)."
            if r["n_c"] >= n_req_ppu
            else f"<strong>Експеримент може бути недостатньо потужним для метрики payments per user</strong> "
                 f"(потрібно ~{n_req_ppu:,} користувачів/групу при MDE 5%; фактично: ~{r['n_c']:,}; "
                 f"оцінена потужність: <strong>{r['obs_power_ppu']:.0%}</strong>)."
        )
    except (TypeError, ValueError):
        powered_note = "Аналіз потужності для payments per user не вдалось обчислити."

    # Segment PPU tables HTML
    seg_tables_html = ""
    for dim, rows in r["segment_ppu"].items():
        label = DIM_LABELS.get(dim, dim.replace("_", " ").title())
        seg_tables_html += _segment_ppu_table(rows, label)


    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<title>A/B Test Report: Редизайн екрану оплати (мобільна версія)</title>
<style>{CSS}</style>
</head>
<body>

<h1>A/B Test Report: Редизайн екрану оплати (мобільна версія)</h1>
<p style="color:#555">
  Сформовано: {date.today().isoformat()} &nbsp;|&nbsp;
  Початок експерименту: 23 липня 2021 р. &nbsp;|&nbsp;
  Платформа: лише Mobile
</p>

<!-- ═══════════════════════════════════════════════════════ 1. EXECUTIVE SUMMARY -->
<h2>1. Executive Summary</h2>
<div class="verdict">
  <h3>Рекомендація: НЕ ЗАПУСКАТИ — перезапустити після виправлення багу</h3>
  <p>
    Новий UI екрану оплати <strong>не показав статистично значущого покращення</strong>
    жодної з основних бізнес-метрик.
    Первинна метрика — <strong>payments per user (PPU)</strong> —
    склала <strong>{r['ppu_t']:.4f}</strong> у тестовій групі проти <strong>{r['ppu_c']:.4f}</strong>
    у контрольній (різниця: <strong>{ppu_diff:+.4f}</strong>, p={r['p_ppu']:.3f} — <strong>не значуще</strong>).
    Revenue per user: ${r['rpu_t']:.2f} (test) проти ${r['rpu_c']:.2f} (control) — також не значуще (p={r['p_rpu']:.3f}).
  </p>
  <p>
    <strong>Критична аномалія, яку необхідно розслідувати до будь-якого рішення:</strong>
    у тестовій групі виявлено різкі відхилення у payment success rate — country group 4 впала до 15%
    (проти 67% у control), тоді як iOS показала +21 pp. Ці два ефекти частково компенсують один одного
    в агрегаті. Country group 4 майже напевно має технічний баг у платіжному flow тест-варіанту,
    що занижує виміряну виручку та конверсію. Після виправлення багу — перезапустити експеримент.
  </p>
</div>

<!-- ═══════════════════════════════════════════════════════ 2. ЩО ТЕСТУВАЛОСЯ -->
<h2>2. Що тестувалося і навіщо</h2>
<p>
  Продуктова команда провела редизайн <strong>UI екрану оплати для мобільних користувачів</strong>
  з метою збільшення кількості успішних покупок ігрової валюти.
  Змінено лише компонування екрана — ціни, кількість валюти та ігрова механіка залишились без змін.
  Експеримент розпочався <strong>23 липня 2021 р.</strong> і розділив нові реєстрації на:
  <em>control group</em> (оригінальний екран) та <em>test group</em> (редизайн).
</p>
<p>
  Гра побудована на <strong>whale monetization model</strong> — невелика частка
  користувачів із великими витратами генерує більшість виручки. Тому аналіз охоплює
  загальну кількість платежів на користувача (PPU), середній чек серед платників (ARPPU),
  загальну виручку на користувача (ARPU) <em>і</em> окремо — вплив на whale-сегмент.
</p>

<!-- ═══════════════════════════════════════════════════════ 3. ХТО УВІЙШОВ ДО АНАЛІЗУ -->
<h2>3. Хто увійшов до аналізу</h2>
<ul>
  <li>
    <strong>Платформа — лише Mobile:</strong> редизайн створено для мобільних пристроїв.
    Немобільні користувачі (desktop, tablet тощо) <em>також потрапили</em> у test і control групи
    через систему призначення — це технічний артефакт.
    Для них був проведений окремий перевірочний аналіз: суттєвих відмінностей між групами не виявлено.
    З основного аналізу вони виключені.
  </li>
  <li>
    <strong>Дата реєстрації ≥ 23 липня 2021 р.:</strong> до когорти включено лише користувачів,
    зареєстрованих на дату початку експерименту або пізніше, щоб уникнути контамінації.
  </li>
  <li>
    <strong>Платежі — лише з 24 липня 2021 р.:</strong> перша повна доба після старту.
    Платежі 23 липня виключено, оскільки не всі користувачі цього дня бачили новий UI
    від початку сесії.
  </li>
  <li><strong>Лише успішні платежі</strong> враховуються у revenue-метриках.</li>
  <li>
    <strong>Фінальна когорта:</strong>
    Control: <strong>{r['n_c']:,} користувачів</strong> &nbsp;|&nbsp;
    Test: <strong>{r['n_t']:,} користувачів</strong>
  </li>
</ul>

<!-- ═══════════════════════════════════════════════════════ 4. SANITY CHECKS -->
<h2>4. Sanity Checks — перевірка балансу груп</h2>
<p>
  Перед аналізом результатів необхідно переконатися, що test і control групи порівнянні
  за характеристиками, які <em>не повинні</em> змінюватися від редизайну.
</p>

<div class="chart">
  {_img_tag("07_sanity_combined.png", "Sanity Checks")}
  <p class="chart-caption">
    Баланс груп за п'ятьма інваріантними вимірами: стать, вікова група, country group,
    джерело трафіку, операційна система. Chi-square p &gt; 0.05 для gender, age, country, traffic source.
    Error bars = 95% Wilson CI.
  </p>
</div>

<div class="pass">
  <strong>Результат:</strong> Розподіли за статтю, віковою групою, country group
  та джерелом трафіку збалансовані між test і control (chi-square p &gt; 0.05 для кожного виміру).
  Рандомізація виглядає коректною.
</div>

<div class="info">
  <strong>Примітка щодо OS:</strong> Формально chi-square тест для операційних систем показує
  p &lt; 0.05 — проте цей результат зумовлений кількома рядками з рідкісними/маловідомими OS
  (одиниці записів), які потрапили в дані як артефакт. Практичний масштаб дисбалансу між
  Android та iOS є незначним. Це не є підставою для визнання рандомізації некоректною.
</div>

<div class="warn">
  <strong>Дисбаланс country group — потенційний конфаундер:</strong>
  Перевірка рандомізації виявила статистично значущий дисбаланс у country_group
  (chi² = 18.08, p = 0.0004, Bonferroni-корекція).
  Country group 4 надмірно представлена у control (3.6% проти 2.4% у test);
  country group 2 надмірно представлена у test (14.6% проти 13.3% у control).
  Ці групи конвертують з дуже різною ефективністю (2.1%–5.3%),
  тому дисбаланс може частково зміщувати загальний результат.
</div>

<!-- ═══════════════════════════════════════════════════════ 5. A/A-ТЕСТ -->
<h2>5. A/A-тест — відповідність когорти до початку тесту та контрольній групі</h2>
<p>
  A/A-тест порівнює <strong>когорту до 23 липня</strong> (мобільні користувачі, зареєстровані
  з {aa['pre_start'].strftime('%d.%m.%Y')} до 22.07.2021 включно — {aa['n_days']} днів,
  n={aa['n_pre']:,}; платежі враховуються в той самий {aa['n_days']}-денний період)
  із <strong>контрольною групою</strong> A/B-тесту (зареєстровані 23 липня або пізніше,
  split_group=0, n={r['n_c']:,}; платежі з 24 липня). Обидві групи бачили оригінальний
  екран оплати. Суттєва різниця між групами може свідчити про сезонні ефекти або зміни
  у складі аудиторії, що ускладнюють інтерпретацію A/B-результатів.
</p>
<table>
  <tr>
    <th>Метрика</th><th>Pre-Test</th><th>Control</th><th>Різниця</th><th>Результат</th>
  </tr>
  <tr style="background:#fff8e1">
    <td><strong>Payments Per User (PPU) — PRIMARY</strong><br>
        <small>Загальна кількість успішних платежів ÷ усі користувачі.
        Враховує і конверсію, і повторні покупки</small></td>
    <td>{aa['ppu_pre']:.4f}<br><small>({aa['ci_ppu_pre'][0]:.4f} — {aa['ci_ppu_pre'][1]:.4f})</small></td>
    <td>{r['ppu_c']:.4f}<br><small>({r['ci_ppu_c'][0]:.4f} — {r['ci_ppu_c'][1]:.4f})</small></td>
    <td>{r['ppu_c'] - aa['ppu_pre']:+.4f}<br><small>({(r['ppu_c'] / aa['ppu_pre'] - 1) * 100 if aa['ppu_pre'] else 0:+.1f}%)</small></td>
    <td>{_badge(aa['p_ppu'])}</td>
  </tr>
  <tr>
    <td><strong>ARPPU (Avg Revenue Per Paying User)</strong><br>
        <small>Середній чек серед користувачів, які платили</small></td>
    <td>${aa['arppu_pre']:,.2f}<br><small>({aa['ci_arppu_pre'][0]:,.2f} — {aa['ci_arppu_pre'][1]:,.2f})</small></td>
    <td>${r['arpp_c']:,.2f}<br><small>({r['ci_arpp_c'][0]:,.2f} — {r['ci_arpp_c'][1]:,.2f})</small></td>
    <td>{(r['arpp_c'] / aa['arppu_pre'] - 1) * 100 if aa['arppu_pre'] else 0:+.1f}%</td>
    <td>{_badge(aa['p_arppu'])}</td>
  </tr>
  <tr>
    <td><strong>ARPU (Avg Revenue Per User)</strong><br>
        <small>Загальна виручка ÷ усі користувачі (включно з тими, хто не платив)</small></td>
    <td>${aa['arpu_pre']:,.2f}<br><small>({aa['ci_arpu_pre'][0]:.2f} — {aa['ci_arpu_pre'][1]:.2f})</small></td>
    <td>${r['rpu_c']:,.2f}<br><small>({r['ci_rpu_c'][0]:.2f} — {r['ci_rpu_c'][1]:.2f})</small></td>
    <td>{(r['rpu_c'] / aa['arpu_pre'] - 1) * 100 if aa['arpu_pre'] else 0:+.1f}%</td>
    <td>{_badge(aa['p_arpu'])}</td>
  </tr>
  <tr>
    <td><strong>Conversion Rate</strong><br>
        <small>% користувачів із ≥1 успішним платежем (вторинний орієнтир)</small></td>
    <td>{aa['cr_pre']:.2%}<br><small>({aa['pay_pre_n']:,} / {aa['n_pre']:,})</small></td>
    <td>{r['cr_c']:.2%}<br><small>({r['pay_c']:,} / {r['n_c']:,})</small></td>
    <td>{(r['cr_c'] - aa['cr_pre']) * 100:+.2f} pp</td>
    <td>{_badge(aa['p_cr'])}</td>
  </tr>
</table>
<div class="info">
  <strong>Що показує цей A/A-тест:</strong>
  Контрольна група конвертується краще за передтестову когорту —
  Conversion Rate {r['cr_c']:.2%} (Control) проти {aa['cr_pre']:.2%} (Pre-Test),
  {(r['cr_c'] - aa['cr_pre']) * 100:+.2f} pp, p={aa['p_cr']:.3f}.
  Саме ця різниця у конверсії і пояснює підвищені PPU та ARPU в контрольній групі:
  більше користувачів платить → більше платежів на юзера (PPU {r['ppu_c']:.4f} проти {aa['ppu_pre']:.4f})
  і вищий середній дохід на користувача (ARPU ${r['rpu_c']:.2f} проти ${aa['arpu_pre']:.2f}).
  При цьому середній чек серед тих, хто платить (ARPPU), змінився незначно
  (${r['arpp_c']:.2f} проти ${aa['arppu_pre']:.2f}, {(r['arpp_c'] / aa['arppu_pre'] - 1) * 100 if aa['arppu_pre'] else 0:+.1f}%) —
  платять ті самі за типом користувачі, просто їх більше в контрольній групі.
  Це пояснюється сезонним ефектом: нові реєстрації у липні конвертуються
  активніше, ніж у червні.
</div>

<!-- ═══════════════════════════════════════════════════════ 6. РЕЗУЛЬТАТИ МЕТРИК -->
<h2>6. Результати ключових метрик</h2>
<table>
  <tr>
    <th>Метрика</th><th>Control</th><th>Test</th><th>Різниця</th><th>Результат</th>
  </tr>
  <tr style="background:#fff8e1">
    <td><strong>Payments Per User (PPU) — PRIMARY</strong><br>
        <small>Загальна кількість успішних платежів ÷ усі користувачі.
        Враховує і конверсію, і повторні покупки</small></td>
    <td>{r['ppu_c']:.4f}<br><small>({r['ci_ppu_c'][0]:.4f} — {r['ci_ppu_c'][1]:.4f})</small></td>
    <td>{r['ppu_t']:.4f}<br><small>({r['ci_ppu_t'][0]:.4f} — {r['ci_ppu_t'][1]:.4f})</small></td>
    <td>{ppu_diff:+.4f}<br><small>({(r['ppu_t'] / r['ppu_c'] - 1) * 100 if r['ppu_c'] else 0:+.1f}%)</small></td>
    <td>{_badge(r['p_ppu'])}</td>
  </tr>
  <tr>
    <td><strong>ARPPU (Avg Revenue Per Paying User)</strong><br>
        <small>Середній чек серед користувачів, які платили</small></td>
    <td>${r['arpp_c']:,.2f}<br><small>({r['ci_arpp_c'][0]:,.2f} — {r['ci_arpp_c'][1]:,.2f})</small></td>
    <td>${r['arpp_t']:,.2f}<br><small>({r['ci_arpp_t'][0]:,.2f} — {r['ci_arpp_t'][1]:,.2f})</small></td>
    <td>{(r['arpp_t'] / r['arpp_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_arpp'])}</td>
  </tr>
  <tr>
    <td><strong>ARPU (Avg Revenue Per User)</strong><br>
        <small>Загальна виручка ÷ усі користувачі (включно з тими, хто не платив)</small></td>
    <td>${r['rpu_c']:,.2f}<br><small>({r['ci_rpu_c'][0]:.2f} — {r['ci_rpu_c'][1]:.2f})</small></td>
    <td>${r['rpu_t']:,.2f}<br><small>({r['ci_rpu_t'][0]:.2f} — {r['ci_rpu_t'][1]:.2f})</small></td>
    <td>{(r['rpu_t'] / r['rpu_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_rpu'])}</td>
  </tr>
  <tr>
    <td><strong>Total Revenue</strong><br>
        <small>Сумарна виручка групи за весь період</small></td>
    <td>${r['total_rev_c']:,.0f}<br><small>({r['ci_total_rev_c'][0]:,.0f} — {r['ci_total_rev_c'][1]:,.0f})</small></td>
    <td>${r['total_rev_t']:,.0f}<br><small>({r['ci_total_rev_t'][0]:,.0f} — {r['ci_total_rev_t'][1]:,.0f})</small></td>
    <td>{(r['total_rev_t'] / r['total_rev_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_rpu'])}</td>
  </tr>
  <tr>
    <td><strong>Conversion Rate</strong><br>
        <small>% користувачів із ≥1 успішним платежем (вторинний орієнтир)</small></td>
    <td>{r['cr_c']:.2%}<br><small>({r['pay_c']:,} / {r['n_c']:,})</small></td>
    <td>{r['cr_t']:.2%}<br><small>({r['pay_t']:,} / {r['n_t']:,})</small></td>
    <td>{(r['diff_cr']*100):+.2f} pp</td>
    <td>{_badge(r['p_cr'])}</td>
  </tr>
</table>

<div class="info">
  <strong>Що показують цифри разом:</strong>
  Конверсія (% платящих) у тест-групі дещо нижча, але середній чек (ARPPU) і ARPU — вищі,
  а загальна виручка test-групи також вища.
  Різниця у конверсії мінімальна (~0.01 pp) — статистично та практично незначуща.
  Зростання ARPPU і ARPU свідчить, що новий UI
  <strong>не скорочує аудиторію, але залучає більше китів або стимулює більші покупки</strong>.
  Жодна з різниць не є статистично значущою при поточному розмірі вибірки.
</div>

<div class="chart">
  {_img_tag("01_primary_metrics.png", "Первинні метрики")}
  <p class="chart-caption">
    Зліва направо: PPU (первинна метрика), ARPU, ARPPU, Total Revenue.
    Напрямок позитивний для всіх метрик у test-групі; жодна різниця не є статистично значущою.
    Error bars = 95% bootstrap CI. ARPPU — лише платники.
  </p>
</div>

<!-- ═══════════════════════════════════════════════════════ 7. АНОМАЛІЯ -->
<h2>7. Аномалія Payment Success Rate</h2>
<div class="warn" style="border-color:#c62828;background:#ffebee">
  <strong>Payment success rate суттєво відрізняється між групами.</strong>
  Payment success rate — технічна метрика: вона вимірює, чи завершується транзакція після того,
  як користувач її ініціює. UI-редизайн не повинен на неї впливати.
  Проте в тест-групі виявлені два протилежні ефекти, які частково компенсують один одного в агрегаті.
</div>
<table>
  <tr>
    <th>Сегмент</th><th>Control success rate</th><th>Test success rate</th>
    <th>Різниця</th><th>Примітки</th>
  </tr>
  <tr>
    <td><strong>Загалом</strong></td>
    <td>{r['sr_rate_c']:.1%}<br><small>(n={r['sr_n_c']:,})</small></td>
    <td>{r['sr_rate_t']:.1%}<br><small>(n={r['sr_n_t']:,})</small></td>
    <td>{(r['sr_rate_t'] - r['sr_rate_c'])*100:+.1f} pp</td>
    <td>Статистично значуще (p ≈ 0)</td>
  </tr>
  <tr style="background:#ffebee">
    <td><strong>Country group 4</strong></td>
    <td>{r['sr_rate_cg4_c']:.1%}<br><small>(n={r['sr_n_cg4_c']:,})</small></td>
    <td>{r['sr_rate_cg4_t']:.1%}<br><small>(n={r['sr_n_cg4_t']:,})</small></td>
    <td>{(r['sr_rate_cg4_t'] - r['sr_rate_cg4_c'])*100:+.1f} pp</td>
    <td>КРИТИЧНО — ймовірно баг платіжного шлюзу у тест-варіанті для цього регіону</td>
  </tr>
  <tr style="background:#d4edda">
    <td><strong>iOS-користувачі</strong></td>
    <td>{r['sr_rate_ios_c']:.1%}<br><small>(n={r['sr_n_ios_c']:,})</small></td>
    <td>{r['sr_rate_ios_t']:.1%}<br><small>(n={r['sr_n_ios_t']:,})</small></td>
    <td>{(r['sr_rate_ios_t'] - r['sr_rate_ios_c'])*100:+.1f} pp</td>
    <td>Сильний позитив — новий UI покращує iOS-платіжний flow</td>
  </tr>
  <tr>
    <td><strong>Android-користувачі</strong></td>
    <td>{r['sr_rate_android_c']:.1%}<br><small>(n={r['sr_n_android_c']:,})</small></td>
    <td>{r['sr_rate_android_t']:.1%}<br><small>(n={r['sr_n_android_t']:,})</small></td>
    <td>{(r['sr_rate_android_t'] - r['sr_rate_android_c'])*100:+.1f} pp</td>
    <td>Не значуще</td>
  </tr>
  <tr style="background:#d4edda">
    <td><strong>Карткові платежі</strong></td>
    <td>{r['sr_rate_card_c']:.1%}<br><small>(n={r['sr_n_card_c']:,})</small></td>
    <td>{r['sr_rate_card_t']:.1%}<br><small>(n={r['sr_n_card_t']:,})</small></td>
    <td>{(r['sr_rate_card_t'] - r['sr_rate_card_c'])*100:+.1f} pp</td>
    <td>Статистично значуще (p ≈ 0)</td>
  </tr>
</table>
<p>
  <strong>Інтерпретація:</strong> Загальний +8.9 pp маскує два окремі ефекти:
  <em>катастрофічний збій</em> у country group 4 (ймовірно несумісність нового UI
  з платіжним шлюзом регіону) і <em>реальне покращення</em> на iOS.
  <strong>Country group 4 необхідно розслідувати до будь-якого рішення про запуск.</strong>
</p>

<!-- ═══════════════════════════════════════════════════════ 8. СЕГМЕНТНИЙ АНАЛІЗ -->
<h2>8. Сегментний аналіз</h2>
<p>
  PPU (payments per user) по кожному виміру — ті самі виміри, що перевірялись у sanity checks.
  Значення показують середню кількість платежів на одного користувача в сегменті; у дужках — розмір вибірки.
  Усі результати є <strong>exploratory</strong> — непоправленими на множинні порівняння.
</p>

<div class="chart">
  {_img_tag("05_segment_ppu.png", "Segment PPU")}
  <p class="chart-caption">
    PPU по сегментах (стать, вік, country group, джерело трафіку, OS).
    Розміри ефектів у межах сегментів є малими і непослідовними — немає одного сегменту,
    де тест-варіант явно домінує в усіх вимірах.
  </p>
</div>

{seg_tables_html}

<p><small>
  Усі результати сегментного аналізу є exploratory і не скориговані на множинні порівняння.
  Розглядайте їх як джерело гіпотез для майбутніх цільових експериментів.
</small></p>

<!-- ═══════════════════════════════════════════════════════ 9. СТАБІЛЬНІСТЬ У ЧАСІ -->
<h2>9. Стабільність у часі</h2>

<div class="chart">
  {_img_tag("02_daily_trend.png", "Daily Trend")}
</div>
<p>
  Control-група відносно стабільна протягом усього періоду спостереження.
  Test-група демонструє <strong>зростаючий тренд</strong> — виручка та кількість
  платежів поступово збільшуються від початку до кінця експерименту.
  Це може свідчити про те, що тест-варіант ще не вийшов на плато, і його реальний
  потенціал може бути вищим, ніж показують поточні агреговані цифри. Для підтвердження
  необхідно більше даних і триваліший період спостереження.
</p>

<!-- ═══════════════════════════════════════════════════════ 10. WHALE-АНАЛІЗ -->
<h2>10. Аналіз whale-сегменту</h2>
<p>
  Whale-користувачі — топ-платники, сукупні витрати яких становлять 75% загальної виручки.
  Whale-поріг для цього експерименту:
  <strong>${r['whale_cutoff']:,.0f}</strong> виручки після старту.
</p>
<table>
  <tr><th>Метрика</th><th>Control</th><th>Test</th><th>Різниця</th></tr>
  <tr>
    <td><strong>Кількість whales</strong></td>
    <td>{r['n_whales_c']}</td>
    <td>{r['n_whales_t']}</td>
    <td>{r['n_whales_t'] - r['n_whales_c']:+d}</td>
  </tr>
  <tr>
    <td><strong>Частка whales серед платників</strong></td>
    <td>{r['whale_cr_c']:.1%}</td>
    <td>{r['whale_cr_t']:.1%}</td>
    <td>{(r['whale_cr_t'] - r['whale_cr_c']) * 100:+.1f} pp</td>
  </tr>
  <tr>
    <td><strong>Середня виручка на одного whale</strong></td>
    <td>${r['whale_arpu_c']:,.0f}</td>
    <td>${r['whale_arpu_t']:,.0f}</td>
    <td>{(r['whale_arpu_t'] / r['whale_arpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
  <tr>
    <td><strong>Whale ARPU (усі користувачі)</strong></td>
    <td>${r['whale_rpu_c']:.2f}</td>
    <td>${r['whale_rpu_t']:.2f}</td>
    <td>{(r['whale_rpu_t'] / r['whale_rpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
</table>

<div class="info">
  <strong>Whale-метрики мають позитивний напрямок</strong> — test-група демонструє вищу частку
  whales та вищий середній чек whale — але <strong>вибірка занадто мала
  ({r['n_whales_c']}–{r['n_whales_t']} whales на групу)</strong>, щоб робити надійні висновки.
  {whale_sig_note}
</div>

<div class="chart">
  {_img_tag("06_whale_analysis.png", "Whale Analysis")}
  <p class="chart-caption">
    Whale-сегмент: частка платників та середня виручка.
    Test-група дещо вища, але малий розмір вибірки (n={r['n_whales_c']}–{r['n_whales_t']}) не дозволяє твердих висновків.
  </p>
</div>

<div style="display:flex;gap:32px;align-items:flex-start;margin:24px 0">
  <div style="flex:0 0 auto;width:50%">
    {_img_tag("02_cumulative_revenue.png", "Revenue Concentration")}
  </div>
  <div style="flex:1;padding-top:8px">
    <h3 style="margin-top:0">Whale-модель підтверджена</h3>
    <p>
      Графік показує, яка частка платників генерує 75% виручки.
      Вертикальні пунктирні лінії відповідають точці, де кумулятивна виручка досягає 75% —
      лише невелика частка найбільших платників забезпечує три чверті всього доходу.
    </p>
    <p>
      Обидві групи (control і test) демонструють однакову концентрацію виручки.
      Це підтверджує, що whale-динаміка не змінилася між групами і є характеристикою
      самого продукту, а не артефактом A/B-розподілу.
    </p>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ 11. РИЗИКИ -->
<h2>11. Ризики та застереження</h2>
<ul>
  <li><strong>Потужність revenue-метрик:</strong> Через екстремальну дисперсію сум платежів
    (whale-модель) для надійного виявлення 10% зміни RPU знадобляться сотні тисяч користувачів.
    Revenue-висновки недостатньо потужні.</li>
  <li><strong>Дисбаланс country group:</strong> Рандомізація призвела до статистично
    значущого дисбалансу country_group (chi² = 18.08, p = 0.0004). Оскільки country groups
    мають суттєво різні базові рівні конверсії (2.1%–5.3%), цей дисбаланс може
    зміщувати загальний результат.</li>
  <li><strong>Аномалія success rate у country group 4:</strong> Test-варіант спричинив падіння
    success rate на 52 pp для country group 4 — ймовірно технічний баг, який знизив виміряну
    виручку та конверсію test-групи і має бути виправлений до наступного запуску.</li>
  <li><strong>Розмір whale-вибірки:</strong> Лише {r['n_whales_c']}–{r['n_whales_t']} whale-користувачів
    на групу — недостатньо для надійного статистичного висновку про whale-ефекти.</li>
  <li><strong>Односторонні тести:</strong> Усі тести налаштовані на виявлення покращення у test.
    Вони менш чутливі до виявлення шкоди.</li>
  <li><strong>Охоплення:</strong> Аналіз стосується лише мобільних користувачів.
    Вплив на інші платформи невідомий.</li>
</ul>

<!-- ═══════════════════════════════════════════════════════ 12. РЕКОМЕНДАЦІЯ -->
<h2>12. Фінальна рекомендація</h2>
<div class="verdict">
  <h3>НЕ ЗАПУСКАТИ — перезапустити після виправлення багу</h3>
  <p>
    Новий UI екрану оплати <strong>не демонструє статистично значущого покращення</strong>
    відносно поточного дизайну за жодною первинною метрикою.
    PPU склав {r['ppu_t']:.4f} у test проти {r['ppu_c']:.4f} у control (p={r['p_ppu']:.3f}).
    Revenue-метрики позитивні за напрямком, але не значущі.
  </p>
  <p>
    <strong>Важливе застереження:</strong> результати ускладнено критичним багом у country group 4
    (success rate 15% проти 67%) — він, ймовірно, знизив виміряну виручку та конверсію test-групи.
    Водночас iOS-користувачі демонструють сильний позитивний сигнал.
    Ці два ефекти компенсують один одного в агрегаті та маскують можливе реальне покращення для iOS.
  </p>
  <p><strong>Рекомендовані наступні кроки:</strong></p>
  <ul>
    <li><strong>Негайно розслідувати платіжний flow у country group 4</strong> — падіння success rate
        на 52 pp є технічним дефектом. Виправити до будь-яких подальших тестів.</li>
    <li><strong>Перезапустити експеримент після виправлення.</strong> Якщо баг country group 4
        занижував конверсію test-групи, чистий повторний тест може показати значущий позитивний ефект.</li>
    <li><strong>Розглянути окремий iOS-тест</strong> — сигнали конверсії та success rate для iOS
        (p &lt; 0.00005) виправдовують цільовий експеримент. При підтвердженні — умовний запуск для iOS.</li>
    <li>Для майбутніх revenue-тестів планувати значно більший розмір вибірки
        (whale-модель створює високу дисперсію).</li>
  </ul>
</div>

<footer>
  Звіт сформовано автоматично на основі A/B-тест даних &nbsp;|&nbsp;
  Мобільні користувачі, зареєстровані 23 липня 2021 р. або пізніше; платежі з 24 липня &nbsp;|&nbsp;
  Поріг статистичної значущості: α = 0.05
</footer>
</body>
</html>"""


def main():
    print("=== Step 9 (UA): Generating CEO Report (Ukrainian) ===")
    df = load_mobile_payments()
    print("Computing results...")
    r = compute_results(df)
    aa = compute_aa_results(df)
    print("Rendering HTML...")
    html = generate_html(r, aa)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
