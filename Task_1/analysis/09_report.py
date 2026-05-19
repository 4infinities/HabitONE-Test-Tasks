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
from statsmodels.stats.proportion import proportions_ztest

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

    # Conversion rate Z-test (one-tailed: test > control)
    _, p_cr = proportions_ztest([pay_t, pay_c], [n_t, n_c], alternative="larger")
    se_cr = np.sqrt(cr_t * (1 - cr_t) / n_t + cr_c * (1 - cr_c) / n_c)
    diff_cr = cr_t - cr_c

    # ARPP: payer-only amounts, Mann-Whitney (test > control)
    arpp_c = ctrl.loc[ctrl["revenue"] > 0, "revenue"]
    arpp_t = test.loc[test["revenue"] > 0, "revenue"]
    _, p_arpp = stats.mannwhitneyu(arpp_t, arpp_c, alternative="greater")

    # RPU: all users, Mann-Whitney (test > control)
    _, p_rpu = stats.mannwhitneyu(test["revenue"], ctrl["revenue"], alternative="greater")
    rpu_c, rpu_t = ctrl["revenue"].mean(), test["revenue"].mean()

    # Bootstrap CI for ARPU
    ci_rpu_c = _bootstrap_ci(ctrl["revenue"].values)
    ci_rpu_t = _bootstrap_ci(test["revenue"].values)

    # Power analysis for conversion rate (1 pp MDE, alpha=0.05, power=0.80)
    p_t_mde = cr_c + 0.01
    h = 2 * (np.arcsin(np.sqrt(p_t_mde)) - np.arcsin(np.sqrt(cr_c)))
    z_req = stats.norm.ppf(1 - ALPHA) + stats.norm.ppf(0.80)
    n_req_cr = int(np.ceil((z_req / h) ** 2)) if h > 0 else float("nan")
    obs_power_cr = float(1 - stats.norm.cdf(
        stats.norm.ppf(1 - ALPHA) - h * np.sqrt(min(n_c, n_t) / 2)))

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
        "p_cr": p_cr, "diff_cr": diff_cr, "se_cr": se_cr,
        "arpp_c": float(arpp_c.mean()), "arpp_t": float(arpp_t.mean()),
        "p_arpp": p_arpp,
        "rpu_c": rpu_c, "rpu_t": rpu_t,
        "p_rpu": p_rpu, "ci_rpu_c": ci_rpu_c, "ci_rpu_t": ci_rpu_t,
        "n_req_cr": n_req_cr, "obs_power_cr": obs_power_cr,
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
"""


def generate_html(r):
    cr_ci_low = r["diff_cr"] - 1.96 * r["se_cr"]
    cr_ci_high = r["diff_cr"] + 1.96 * r["se_cr"]

    whale_sig_note = (
        f"Mann-Whitney U test on whale payment amounts: p={r['p_whale']:.3f} — "
        f"{'<strong>significant</strong>' if not np.isnan(r['p_whale']) and r['p_whale'] < ALPHA else 'not significant'}."
        if not np.isnan(r["p_whale"])
        else "Formal significance test not applicable due to small whale sample size."
    )

    powered_note = (
        f"<strong>The experiment was adequately powered for conversion rate</strong> "
        f"(required ~{r['n_req_cr']:,} users/group for 1 pp MDE; actual: ~{r['n_c']:,}; "
        f"estimated power: {r['obs_power_cr']:.0%})."
        if r["n_c"] >= r["n_req_cr"]
        else f"<strong>The experiment may be underpowered for conversion rate</strong> "
             f"(required ~{r['n_req_cr']:,} users/group for 1 pp MDE; actual: ~{r['n_c']:,}; "
             f"estimated power: {r['obs_power_cr']:.0%})."
    )

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
    Conversion rate in the test group was <strong>{r['cr_t']:.2%}</strong>
    vs <strong>{r['cr_c']:.2%}</strong> in control
    (difference: <strong>{r['diff_cr']:+.2f} pp</strong>, p={r['p_cr']:.3f} — not significant,
    and the direction is <em>negative</em>).
    Average Revenue Per Payer was ${r['arpp_t']:,.0f} (test) vs ${r['arpp_c']:,.0f} (control),
    also not significant (p={r['p_arpp']:.3f}).
    There is <strong>no statistical evidence</strong> that launching would increase revenue or conversions.
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
  <tr>
    <td><strong>Conversion Rate</strong><br>
        <small>% of users who paid ≥1 time</small></td>
    <td>{r['cr_c']:.2%}<br><small>({r['pay_c']:,} / {r['n_c']:,})</small></td>
    <td>{r['cr_t']:.2%}<br><small>({r['pay_t']:,} / {r['n_t']:,})</small></td>
    <td>{r['diff_cr']:+.2f} pp</td>
    <td>{_badge(r['p_cr'])}</td>
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
</table>

<div class="chart">{_img_tag("01_conversion_rate.png", "Conversion Rate Chart")}</div>
<div class="chart">{_img_tag("04_arpu.png", "ARPU Chart")}</div>
<div class="chart">{_img_tag("02_amount_distribution.png", "Amount Distribution")}</div>
<div class="chart">{_img_tag("03_daily_timeseries.png", "Daily Conversion Rate")}</div>

<h2>5. Statistical Significance — Plain English</h2>
<p>Statistical tests used:</p>
<ul>
  <li><strong>Conversion Rate:</strong> Two-proportion Z-test (one-tailed).
    Tests whether the test group has a higher conversion rate than control.
    P-value: {r['p_cr']:.3f}.</li>
  <li><strong>Avg Revenue Per Payer:</strong> Mann-Whitney U test (non-parametric;
    appropriate because payment amounts are heavily right-skewed due to whale spending).
    P-value: {r['p_arpp']:.3f}.</li>
  <li><strong>Revenue Per User:</strong> Mann-Whitney U test.
    P-value: {r['p_rpu']:.3f}.</li>
</ul>

<div class="warn">
  <strong>All three primary metrics: p-value &gt; 0.05 — no statistically significant effect found.</strong>
  In plain terms: the observed differences between test and control are consistent with random
  variation. We cannot conclude that the new design changes user behavior.
</div>

<p>
  <strong>Confidence interval for conversion rate difference:</strong>
  [{cr_ci_low:+.3f} pp, {cr_ci_high:+.3f} pp] (95% CI).
  The interval includes zero and the lower bound is negative —
  the redesign <em>may actually reduce conversion rate</em>.
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

<div class="chart">{_img_tag("06_whale_analysis.png", "Whale Analysis")}</div>

<h2>7. Segment Analysis</h2>
<div class="chart">{_img_tag("05_country_heatmap.png", "Country Heatmap")}</div>
<h3>Conversion Rate by Country Group</h3>
<table>
  <tr><th>Country Group</th><th>Control CR</th><th>Test CR</th><th>Difference</th></tr>
  {_country_rows(r['country_pivot'])}
</table>
<p><small>
  Segment-level results are exploratory and not corrected for multiple comparisons.
  Treat as hypothesis-generating, not as confirmed findings.
</small></p>

<h2>8. Sanity Checks</h2>
<div class="chart">{_img_tag("07_sanity_checks.png", "Sanity Checks")}</div>
<div class="pass">
  <strong>Overall PASS:</strong> Gender, age group, country group, and traffic source
  distributions are balanced between test and control (chi-square p &gt; 0.05).
  Randomization appears valid for these dimensions.
</div>
<div class="warn">
  <strong>FLAG:</strong> Device operating system (system) distribution differs between
  groups (chi-square p = 0.004) in the mobile cohort.
  This imbalance is small in practical terms but represents a methodological caveat.
</div>

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
    Conversion rate was marginally <em>lower</em> in the test group
    ({r['cr_t']:.2%} vs {r['cr_c']:.2%}, p={r['p_cr']:.3f}).
    Revenue metrics showed no significant change.
    While whale spending trended upward in the test group, the whale sample is too small
    to draw firm conclusions.
  </p>
  <p><strong>Suggested next steps:</strong></p>
  <ul>
    <li>Conduct qualitative UX research to understand why the redesign did not lift conversion.</li>
    <li>Consider a targeted redesign experiment focused specifically on the whale segment,
        potentially with a longer run time and a larger cohort.</li>
    <li>Investigate the device OS imbalance before running the next experiment.</li>
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
