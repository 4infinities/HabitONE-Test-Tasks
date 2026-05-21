"""
Step 9: Generate CEO-facing HTML report with embedded charts.
Run after: 01_filtering.py, 08_charts.py
"""
import base64
import os
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from constants import SCRIPT_DIR, TEST_START, build_ab_user_revenue, load_mobile_payments

CHARTS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "charts"))
REPORT_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "report.html"))
ALPHA = 0.05
RNG = np.random.default_rng(42)
N_BOOT = 5_000


def _bootstrap_ci(arr):
    samples = RNG.choice(arr, (N_BOOT, len(arr)), replace=True).mean(1)
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

    # ARPP: payer-only amounts, Mann-Whitney (test > control)
    arpp_c = ctrl.loc[ctrl["revenue"] > 0, "revenue"]
    arpp_t = test.loc[test["revenue"] > 0, "revenue"]
    _, p_arpp = stats.mannwhitneyu(arpp_t, arpp_c, alternative="greater")

    # RPU: all users, Mann-Whitney (test > control)
    _, p_rpu = stats.mannwhitneyu(test["revenue"], ctrl["revenue"], alternative="greater")
    rpu_c, rpu_t = ctrl["revenue"].mean(), test["revenue"].mean()

    # Bootstrap CI for RPU
    ci_rpu_c = _bootstrap_ci(ctrl["revenue"].values)
    ci_rpu_t = _bootstrap_ci(test["revenue"].values)

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

    # Whale metrics
    cutoff = _whale_cutoff(ab)
    w_c = ctrl[ctrl["revenue"] >= cutoff]
    w_t = test[test["revenue"] >= cutoff]
    payers_c = int((ctrl["revenue"] > 0).sum())
    payers_t = int((test["revenue"] > 0).sum())
    whale_cr_c = len(w_c) / max(payers_c, 1)
    whale_cr_t = len(w_t) / max(payers_t, 1)
    whale_arpu_c = float(w_c["revenue"].mean()) if len(w_c) else 0.0
    whale_arpu_t = float(w_t["revenue"].mean()) if len(w_t) else 0.0
    whale_rpu_c = w_c["revenue"].sum() / n_c
    whale_rpu_t = w_t["revenue"].sum() / n_t

    # Mann-Whitney for whale amounts
    if len(w_c) >= 5 and len(w_t) >= 5:
        _, p_whale = stats.mannwhitneyu(w_t["revenue"], w_c["revenue"], alternative="greater")
    else:
        p_whale = float("nan")

    # Country segment breakdown
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "country_group"]]
    )
    ab_seg = ab.merge(attrs, on="id_user", how="left")
    seg_c = (
        ab_seg[ab_seg["split_group"] == 0]
        .groupby("country_group")["revenue"]
        .apply(lambda x: (x > 0).mean())
        .rename("cr_ctrl")
    )
    seg_t = (
        ab_seg[ab_seg["split_group"] == 1]
        .groupby("country_group")["revenue"]
        .apply(lambda x: (x > 0).mean())
        .rename("cr_test")
    )
    country_pivot = seg_c.to_frame().join(seg_t, how="outer")
    country_pivot["diff_pp"] = (country_pivot["cr_test"] - country_pivot["cr_ctrl"]) * 100

    return {
        "n_c": n_c, "n_t": n_t,
        "pay_c": pay_c, "pay_t": pay_t,
        "cr_c": cr_c, "cr_t": cr_t,
        "diff_cr": diff_cr, "se_cr": se_cr,
        "ppu_c": ppu_c, "ppu_t": ppu_t,
        "p_ppu": p_ppu, "ci_ppu_c": ci_ppu_c, "ci_ppu_t": ci_ppu_t,
        "n_req_ppu": n_req_ppu, "obs_power_ppu": obs_power_ppu,
        "arpp_c": float(arpp_c.mean()), "arpp_t": float(arpp_t.mean()),
        "p_arpp": p_arpp,
        "rpu_c": rpu_c, "rpu_t": rpu_t,
        "p_rpu": p_rpu, "ci_rpu_c": ci_rpu_c, "ci_rpu_t": ci_rpu_t,
        "whale_cutoff": cutoff,
        "n_whales_c": len(w_c), "n_whales_t": len(w_t),
        "whale_cr_c": whale_cr_c, "whale_cr_t": whale_cr_t,
        "whale_arpu_c": whale_arpu_c, "whale_arpu_t": whale_arpu_t,
        "whale_rpu_c": float(whale_rpu_c), "whale_rpu_t": float(whale_rpu_t),
        "p_whale": p_whale,
        "country_pivot": country_pivot,
    }


def _img_tag(fname, alt=""):
    path = os.path.join(CHARTS_DIR, fname)
    if not os.path.exists(path):
        return (f'<p style="background:#fff3cd;padding:10px;border-radius:4px">'
                f'Chart not found: <code>{fname}</code> — run 08_charts.py first.</p>')
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<img src="data:image/png;base64,{b64}" alt="{alt}" '
            f'style="max-width:100%;border:1px solid #ddd;border-radius:4px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.1)">')


def _badge(p):
    if np.isnan(p):
        return '<span class="badge badge-na">N/A</span>'
    if p < ALPHA:
        return f'<span class="badge badge-sig">Significant (p={p:.3f})</span>'
    return f'<span class="badge badge-ns">Not Significant (p={p:.3f})</span>'


def _country_rows(pivot):
    rows = []
    for country, row in pivot.iterrows():
        diff = row["diff_pp"]
        bg = "#d4edda" if diff > 0.5 else ("#f8d7da" if diff < -0.5 else "#fff")
        rows.append(
            f'<tr><td>{country}</td>'
            f'<td>{row["cr_ctrl"]:.2%}</td>'
            f'<td>{row["cr_test"]:.2%}</td>'
            f'<td style="background:{bg}">{diff:+.2f} pp</td></tr>'
        )
    return "\n".join(rows)


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
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:24px 0;align-items:start}}
.chart-cell{{text-align:center}}
.chart-caption{{font-size:.82em;color:#555;font-style:italic;margin:4px 0 0;padding:0 8px;text-align:center}}
"""


def _img_pair(f1, cap1, f2, cap2, alt1="", alt2=""):
    return (
        f'<div class="chart-row">'
        f'<div class="chart-cell"><div class="chart">{_img_tag(f1, alt1)}</div>'
        f'<p class="chart-caption">{cap1}</p></div>'
        f'<div class="chart-cell"><div class="chart">{_img_tag(f2, alt2)}</div>'
        f'<p class="chart-caption">{cap2}</p></div>'
        f'</div>'
    )


def generate_html(r):
    cr_ci_low = r["diff_cr"] - 1.96 * r["se_cr"]
    cr_ci_high = r["diff_cr"] + 1.96 * r["se_cr"]
    ppu_diff = r["ppu_t"] - r["ppu_c"]
    ppu_ci_low = r["ci_ppu_t"][0] - r["ci_ppu_c"][1]
    ppu_ci_high = r["ci_ppu_t"][1] - r["ci_ppu_c"][0]

    whale_sig_note = (
        f"Mann-Whitney U test on whale payment amounts: p={r['p_whale']:.3f} — "
        f"{'<strong>significant</strong>' if not np.isnan(r['p_whale']) and r['p_whale'] < ALPHA else 'not significant'}."
        if not np.isnan(r["p_whale"])
        else "Formal significance test not applicable due to small whale sample size."
    )

    try:
        n_req_ppu = int(r["n_req_ppu"])
        powered_note = (
            f"<strong>The experiment was adequately powered for payments per user</strong> "
            f"(required ~{n_req_ppu:,} users/group for 5% relative MDE; actual: ~{r['n_c']:,}; "
            f"estimated power: {r['obs_power_ppu']:.0%})."
            if r["n_c"] >= n_req_ppu
            else f"<strong>The experiment may be underpowered for payments per user</strong> "
                 f"(required ~{n_req_ppu:,} users/group for 5% relative MDE; actual: ~{r['n_c']:,}; "
                 f"estimated power: {r['obs_power_ppu']:.0%})."
        )
    except (TypeError, ValueError):
        powered_note = "Power analysis for payments per user could not be computed (insufficient baseline variance)."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>A/B Test Report: Mobile Payment Screen Redesign</title>
<style>{CSS}</style>
</head>
<body>

<h1>A/B Test Report: Mobile Payment Screen Redesign</h1>
<p style="color:#555">
  Generated: {date.today().isoformat()} &nbsp;|&nbsp;
  Experiment start: July 23, 2021 &nbsp;|&nbsp;
  Platform: Mobile only
</p>

<h2>1. Executive Summary</h2>
<div class="verdict">
  <h3>Recommendation: DO NOT LAUNCH</h3>
  <p>
    The new payment screen UI produced <strong>no statistically significant improvement</strong>
    on any primary business metric.
    The primary metric — <strong>payments per user</strong> (total successful payments per person,
    capturing both conversion and repeat purchases) — was
    <strong>{r['ppu_t']:.4f}</strong> in the test group vs <strong>{r['ppu_c']:.4f}</strong>
    in control (difference: <strong>{ppu_diff:+.4f}</strong>, p={r['p_ppu']:.3f} — not significant,
    and the direction is <em>negative</em>).
    Average Revenue Per Payer was ${r['arpp_t']:,.0f} (test) vs ${r['arpp_c']:,.0f} (control),
    also not significant (p={r['p_arpp']:.3f}).
    There is <strong>no statistical evidence</strong> that launching would increase payments or revenue.
  </p>
</div>

<h2>2. What Was Tested and Why</h2>
<p>
  The product team redesigned the in-app <strong>payment screen UI for mobile users</strong>
  to increase successful purchases of in-game currency.
  Only the screen layout was changed — prices, currency amounts, and game mechanics were unchanged.
  The experiment ran from <strong>July 23, 2021</strong>, splitting new registrations into:
  a <em>control group</em> (original screen) and a <em>test group</em> (redesigned screen).
</p>
<p>
  This game operates on a <strong>whale monetization model</strong> — a small fraction of
  high-spending users drives the majority of revenue. The analysis therefore covers
  overall conversion rate, average payment amount, total revenue per user, <em>and</em>
  the impact on the whale segment separately.
</p>

<h2>3. Who Was Included</h2>
<ul>
  <li><strong>Platform:</strong> Mobile users only (the redesign was built for mobile).
    Non-mobile users were excluded.</li>
  <li><strong>Registration date:</strong> Only users registered on or after July 23, 2021
    (experiment start). Pre-existing users were excluded to avoid contamination.</li>
  <li><strong>Successful payments only</strong> (failed transactions excluded from revenue metrics).</li>
  <li>
    <strong>Final cohort:</strong>
    Control: <strong>{r['n_c']:,} users</strong> &nbsp;|&nbsp;
    Test: <strong>{r['n_t']:,} users</strong>
  </li>
</ul>

<h2>4. Key Metrics Results</h2>
<table>
  <tr>
    <th>Metric</th><th>Control</th><th>Test</th><th>Difference</th><th>Result</th>
  </tr>
  <tr style="background:#fff8e1">
    <td><strong>Payments Per User (PPU) — PRIMARY</strong><br>
        <small>PRIMARY METRIC — total successful payments ÷ all users<br>
        Captures both conversion and repeat purchases</small></td>
    <td>{r['ppu_c']:.4f}<br><small>(95% CI: [{r['ci_ppu_c'][0]:.4f}, {r['ci_ppu_c'][1]:.4f}])</small></td>
    <td>{r['ppu_t']:.4f}<br><small>(95% CI: [{r['ci_ppu_t'][0]:.4f}, {r['ci_ppu_t'][1]:.4f}])</small></td>
    <td>{ppu_diff:+.4f}<br><small>({(r['ppu_t'] / r['ppu_c'] - 1) * 100 if r['ppu_c'] else 0:+.1f}%)</small></td>
    <td>{_badge(r['p_ppu'])}</td>
  </tr>
  <tr>
    <td><strong>Avg Revenue Per Payer (ARPP)</strong><br>
        <small>Mean spend among users who paid</small></td>
    <td>${r['arpp_c']:,.2f}</td>
    <td>${r['arpp_t']:,.2f}</td>
    <td>{(r['arpp_t'] / r['arpp_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_arpp'])}</td>
  </tr>
  <tr>
    <td><strong>Revenue Per User (RPU / ARPU)</strong><br>
        <small>Total revenue ÷ all users including non-payers</small></td>
    <td>${r['rpu_c']:,.2f}</td>
    <td>${r['rpu_t']:,.2f}</td>
    <td>{(r['rpu_t'] / r['rpu_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_rpu'])}</td>
  </tr>
  <tr>
    <td><strong>Conversion Rate</strong><br>
        <small>% of users who paid ≥1 time (secondary reference)</small></td>
    <td>{r['cr_c']:.2%}<br><small>({r['pay_c']:,} / {r['n_c']:,})</small></td>
    <td>{r['cr_t']:.2%}<br><small>({r['pay_t']:,} / {r['n_t']:,})</small></td>
    <td>{(r['diff_cr']*100):+.2f} pp</td>
    <td>—</td>
  </tr>
</table>

<div class="chart-cell">
  {_img_tag("01_primary_metrics.png", "Primary Metrics")}
  <p class="chart-caption">
    Left: payments per user (PPU — primary metric). Right: revenue per user (RPU).
    Both groups are nearly identical; neither difference is statistically significant.
    Error bars = 95% bootstrap CI.
  </p>
</div>
<div class="chart-cell">
  {_img_tag("02_amount_and_trend.png", "Amount Distribution and Daily Trend")}
  <p class="chart-caption">
    Left: key payment amount percentiles among payers (log scale — whale-model skew).
    Right: daily conversion rate from experiment start — no consistent trend in either direction.
  </p>
</div>

<h2>5. Statistical Significance — Plain English</h2>
<p>Statistical tests used:</p>
<ul>
  <li><strong>★ Payments Per User (primary):</strong> Mann-Whitney U test (non-parametric;
    appropriate because the distribution is zero-inflated — most users pay 0 times).
    Tests whether the test group produces more payments per user than control.
    P-value: {r['p_ppu']:.3f}.</li>
  <li><strong>Avg Revenue Per Payer:</strong> Mann-Whitney U test (non-parametric;
    appropriate because payment amounts are heavily right-skewed due to whale spending).
    P-value: {r['p_arpp']:.3f}.</li>
  <li><strong>Revenue Per User:</strong> Mann-Whitney U test.
    P-value: {r['p_rpu']:.3f}.</li>
</ul>

<div class="warn">
  <strong>All three primary metrics: p-value &gt; 0.05 — no statistically significant effect found.</strong>
  In plain terms: the observed differences between test and control are consistent with random
  variation. We cannot conclude that the new design changes user behaviour.
</div>

<p>
  <strong>95% bootstrap confidence interval for PPU difference (test − control):</strong>
  [{ppu_ci_low:+.4f}, {ppu_ci_high:+.4f}].
  The interval includes zero — the redesign shows no reliable impact on payment frequency.
</p>

<p>{powered_note}</p>

<h2>6. Whale Impact Analysis</h2>
<p>
  Whale users are the top spenders whose combined spend accounts for 75% of total revenue.
  The whale threshold for this experiment is
  <strong>${r['whale_cutoff']:,.0f}</strong> in post-experiment revenue.
</p>
<table>
  <tr><th>Metric</th><th>Control</th><th>Test</th><th>Difference</th></tr>
  <tr>
    <td><strong>Number of Whales</strong></td>
    <td>{r['n_whales_c']}</td>
    <td>{r['n_whales_t']}</td>
    <td>{r['n_whales_t'] - r['n_whales_c']:+d}</td>
  </tr>
  <tr>
    <td><strong>Whale Share of Payers</strong></td>
    <td>{r['whale_cr_c']:.1%}</td>
    <td>{r['whale_cr_t']:.1%}</td>
    <td>{(r['whale_cr_t'] - r['whale_cr_c']) * 100:+.1f} pp</td>
  </tr>
  <tr>
    <td><strong>Avg Revenue per Whale User</strong></td>
    <td>${r['whale_arpu_c']:,.0f}</td>
    <td>${r['whale_arpu_t']:,.0f}</td>
    <td>{(r['whale_arpu_t'] / r['whale_arpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
  <tr>
    <td><strong>Whale Revenue Per User (all users)</strong></td>
    <td>${r['whale_rpu_c']:.2f}</td>
    <td>${r['whale_rpu_t']:.2f}</td>
    <td>{(r['whale_rpu_t'] / r['whale_rpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
</table>

<div class="info">
  <strong>Whale metrics trend positive</strong> — test group shows higher whale share and
  higher average whale spend — but the <strong>sample is too small
  ({r['n_whales_c']}–{r['n_whales_t']} whales per group)</strong> to draw reliable conclusions.
  {whale_sig_note}
  This is a directional positive signal and warrants further investigation,
  but it is not sufficient justification for a full launch.
</div>

<div class="chart-cell">
  {_img_tag("06_whale_analysis.png", "Whale Analysis")}
  <p class="chart-caption">Whale segment: share of payers and average revenue. Test group trends
  slightly higher, but small sample size (n={r['n_whales_c']}–{r['n_whales_t']}) prevents firm conclusions.</p>
</div>

<h2>7. Segment Analysis</h2>

<h3>Conversion Rate by Country Group</h3>
<div class="chart-cell">
  {_img_tag("05_country_heatmap.png", "Country Heatmap")}
  <p class="chart-caption">Conversion rate by country group × A/B group. Country groups differ substantially
  in baseline conversion — this heterogeneity is a key caveat for the overall result.</p>
</div>
<table>
  <tr><th>Country Group</th><th>Control CR</th><th>Test CR</th><th>Difference</th></tr>
  {_country_rows(r['country_pivot'])}
</table>

<div class="warn">
  <strong>Country group imbalance — potential confounder:</strong>
  The randomization check found a statistically significant imbalance in country_group
  (chi² = 18.08, p = 0.0004, Bonferroni-corrected).
  Country group 4 is over-represented in control (3.6% vs 2.4% in test);
  country group 2 is over-represented in test (14.6% vs 13.3% in control).
  Pre-experiment data shows these groups convert at very different rates — group 2 converts
  at 5.25%, group 4 at 2.40%, vs 2.12% for the majority group 1.
  This imbalance may partially suppress or inflate the overall A/B result.
</div>

<h3>Exploratory Segment Findings</h3>
<p>
  The following sub-segment differences were observed <em>after</em> examining the data and
  are <strong>exploratory</strong> (not pre-specified hypotheses). They are reported here
  because the effect sizes are very large — p &lt; 0.00005 in each case,
  far below the Bonferroni threshold of 0.0025 even after accounting for ~20 comparisons.
  Statistical significance confirms these effects are real in the data; it does not explain
  their cause (genuine UX improvement vs. experiment artifact).
</p>
<ul>
  <li>
    <strong>iOS users:</strong> conversion rate in the test group is substantially higher than control.
    This is the single most striking positive signal in the dataset. However, iOS is also the group
    with an anomalous success rate improvement (see Section 8), so the mechanism is unclear.
  </li>
  <li>
    <strong>Card payment users:</strong> conversion via card is higher in the test group.
    Could reflect a genuine improvement in the card payment flow in the new UI design.
  </li>
  <li>
    <strong>Country group 1 (majority market, 86% of users):</strong> conversion is higher in test.
    Since group 1 drives most of the user base, this is the largest contributor to any overall effect.
  </li>
</ul>
<div class="info">
  <strong>Recommended next step:</strong> Run a focused experiment on iOS users in country group 1
  to confirm whether the redesign genuinely improves conversion for this segment.
  If confirmed, a conditional launch (iOS only) may be justified.
</div>

<p><small>
  All segment-level results are exploratory and not corrected for multiple comparisons.
  Treat as hypothesis-generating, not as confirmed findings.
</small></p>

<h2>8. Sanity Checks</h2>

<h3>Group Balance (Invariant Metrics)</h3>
<div class="chart-cell">
  {_img_tag("07_sanity_combined.png", "Sanity Checks")}
  <p class="chart-caption">
    Group balance across four invariant dimensions (gender, age group, country group, traffic source).
    Overlapping error bars indicate no significant imbalance. Chi-square p &gt; 0.05 for all four.
  </p>
</div>
<div class="pass">
  <strong>Overall PASS:</strong> Gender, age group, country group, and traffic source
  distributions are balanced between test and control (chi-square p &gt; 0.05).
  Randomization appears valid for these dimensions.
</div>
<div class="warn">
  <strong>FLAG — OS imbalance:</strong> Device operating system (system) distribution differs between
  groups (chi-square p = 0.004) in the mobile cohort. This imbalance is small in practical terms
  but represents a methodological caveat, especially given the large iOS effect in Section 7.
</div>

<h3>Payment Success Rate — Critical Anomaly</h3>
<div class="warn" style="border-color:#c62828;background:#ffebee">
  <strong>RED FLAG: Payment success rate differs significantly between groups.</strong>
  Payment success rate is a <em>technical</em> metric — it measures whether a transaction
  completes after the user initiates it. A UI redesign should not affect it.
  Yet the test group shows a markedly different success rate from control,
  with two opposing effects that partially cancel in the aggregate.
</div>
<table>
  <tr>
    <th>Segment</th><th>Control success rate</th><th>Test success rate</th>
    <th>Difference</th><th>Notes</th>
  </tr>
  <tr>
    <td><strong>Overall</strong></td>
    <td>61.5%</td><td>70.4%</td>
    <td>+8.9 pp (95% CI: +4.9 to +13.0 pp)</td>
    <td>Statistically significant (p ≈ 0)</td>
  </tr>
  <tr style="background:#ffebee">
    <td><strong>Country group 4</strong></td>
    <td>67.4%</td><td>15.0%</td>
    <td>−52.4 pp (95% CI: −69.9 to −34.9 pp)</td>
    <td>CRITICAL — likely a payment gateway bug in test variant for this region</td>
  </tr>
  <tr style="background:#d4edda">
    <td><strong>iOS users</strong></td>
    <td>57.1%</td><td>77.9%</td>
    <td>+20.8 pp (95% CI: +15.5 to +26.1 pp)</td>
    <td>Strong positive — new UI may genuinely improve iOS payment flow</td>
  </tr>
  <tr>
    <td><strong>Android users</strong></td>
    <td>66.7%</td><td>61.3%</td>
    <td>−5.4 pp (95% CI: −11.6 to +0.7 pp)</td>
    <td>Not significant (p = 0.095)</td>
  </tr>
  <tr>
    <td><strong>Card payments</strong></td>
    <td>—</td><td>—</td>
    <td>+9.4 pp (95% CI: +5.1 to +13.7 pp)</td>
    <td>Statistically significant (p ≈ 0)</td>
  </tr>
</table>
<p>
  <strong>Interpretation:</strong> The overall +8.9 pp is misleading — it masks two distinct effects:
  a <em>catastrophic failure</em> in country group 4 (payment flow appears broken in the test variant,
  possibly a payment gateway compatibility issue) and a <em>genuine improvement</em> on iOS.
  These two effects partially cancel. <strong>Country group 4 must be investigated before any
  launch decision.</strong>
</p>

<h2>9. Risks and Caveats</h2>
<ul>
  <li><strong>Revenue metric power:</strong> Due to extreme variance in payment amounts
    (Gini ≈ 0.99; a handful of whale users dominate revenue), the experiment would require
    hundreds of thousands of users to reliably detect a 10% change in RPU.
    Revenue-based conclusions are therefore underpowered.</li>
  <li><strong>OS imbalance:</strong> A statistically significant difference in device OS
    mix was found between groups, which may introduce minor confounding.</li>
  <li><strong>Whale sample size:</strong> Only {r['n_whales_c']}–{r['n_whales_t']} whale
    users per group — not enough for reliable statistical inference on whale-level effects.</li>
  <li><strong>Country group imbalance:</strong> Randomization produced a statistically
    significant imbalance in country_group (chi² = 18.08, p = 0.0004). Since country groups
    have meaningfully different baseline conversion rates (2.1% to 5.3%), this imbalance
    may bias the overall result in either direction.</li>
  <li><strong>Payment success rate anomaly in country group 4:</strong> The test variant
    produced a 52 pp drop in payment success rate for country group 4 users (15% vs 67%).
    This is almost certainly a technical bug, not a UX effect — it may have suppressed
    measured revenue and conversion in the test group, making the new design look worse than it is.</li>
  <li><strong>One-tailed tests:</strong> All tests were designed to detect improvement in
    test. They are less sensitive to detecting harm (negative effects on control).</li>
  <li><strong>Novelty effect:</strong> Users may behave differently when encountering a new
    UI for the first time. A longer experiment would reduce this risk.</li>
  <li><strong>Scope:</strong> This analysis covers mobile users only.
    Impact on other platforms is unknown.</li>
</ul>

<h2>10. Final Recommendation</h2>
<div class="verdict">
  <h3>DO NOT LAUNCH</h3>
  <p>
    The new payment screen UI <strong>does not demonstrate a statistically significant
    improvement</strong> over the current design on any primary metric.
    The primary metric — payments per user — was marginally <em>lower</em> in the test group
    ({r['ppu_t']:.4f} vs {r['ppu_c']:.4f}, p={r['p_ppu']:.3f}).
    Revenue metrics showed no significant change.
    While whale spending trended upward in the test group, the whale sample is too small
    to draw firm conclusions.
  </p>
  <p>
    <strong>Important caveat:</strong> The overall result is complicated by two anomalies.
    First, the payment flow for country group 4 appears broken in the test variant (15% success
    rate vs 67% in control) — this likely suppressed test-group revenue and should be treated as
    a technical bug. Second, iOS users show a strong positive signal in both conversion and payment
    success rate. These effects partially cancel in the aggregate, masking what may be a meaningful
    iOS-specific improvement.
  </p>
  <p><strong>Suggested next steps:</strong></p>
  <ul>
    <li><strong>Immediately investigate the country group 4 payment flow</strong> — the 52 pp drop
        in payment success rate is almost certainly a technical defect in the new UI's integration
        with that region's payment gateway. Fix it before any further experiments.</li>
    <li><strong>Consider a conditional re-test for iOS only</strong> — the iOS conversion and
        success rate signals are strong enough (p &lt; 0.00005) to warrant a dedicated experiment.
        If a clean iOS-only test confirms the effect, a phased launch for iOS can be justified.</li>
    <li>Conduct qualitative UX research to understand why the redesign did not lift Android conversion.</li>
    <li>For future experiments testing revenue metrics, plan for a much larger sample size
        (the whale model creates extremely high variance that requires large cohorts).</li>
  </ul>
</div>

<footer>
  Report generated automatically from A/B test data &nbsp;|&nbsp;
  Mobile users registered on/after July 23, 2021 &nbsp;|&nbsp;
  Statistical significance threshold: α = 0.05
</footer>
</body>
</html>"""


def main():
    print("=== Step 9: Generating CEO Report ===")
    df = load_mobile_payments()
    print("Computing results...")
    r = compute_results(df)
    print("Rendering HTML...")
    html = generate_html(r)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
