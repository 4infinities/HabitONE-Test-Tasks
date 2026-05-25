# CLAUDE.md — A/B Test: Mobile Payment Screen Redesign

## 🎯 Project Goal

A game design team proposed a **new payment screen UI for mobile users** to increase the number of successful purchases of in-game currency (players pay real money).  
The new variant was rolled out to a test group **starting July 23, 00:00**.  
A control group continued seeing the original screen.

**Business Question:**  
> Should the new payment screen be launched for all users, or should it be rejected?  
> Answer must be backed by charts and statistical calculations.

**Final Deliverable:**  
A self-explanatory PDF/HTML report for the CEO — no technical background assumed.  
The report must contain: key findings, visualizations, statistical conclusions, and a clear recommendation (launch / do not launch).

---

## 🏢 Business Context

- **Product type:** Mobile game with in-game currency purchases (real money → virtual currency)
- **Monetization model:** Whale model — a small segment of high-paying users (~5%) drives the majority of revenue (>60%). The redesign must be evaluated not only on conversion rate but also on **payment amount per payer** and **impact on whale segment**.
- **Change scope:** Only the **payment screen UI** was changed — no changes to pricing, currency amounts, or game mechanics.
- **Experiment start date:** July 23, 00:00
- **Target platform:** Mobile users only (the redesign was built for mobile)

---

## 📁 Data

**File:** `raw_data` (provided separately, likely CSV)

### Data Dictionary

| Column | Description |
|---|---|
| `id_user` | Unique user identifier |
| `gender` | User gender |
| `date_reg` | User registration datetime |
| `platform` | User platform (mobile, desktop, tablet, etc.) |
| `id_traffic_source` | Ad platform / acquisition source |
| `country_group` | Country group |
| `age_group` | Age group |
| `system` | Device operating system |
| `date_payment` | Payment datetime (NULL = user never paid) |
| `method` | Payment method |
| `amount` | Payment amount |
| `successful_payment` | 1 if payment was successful, 0 otherwise |
| `split_group` | A/B group marker: **1 = test group**, 0 = control group |

> **Important:** Rows with `date_payment` = NULL represent registered users who never made a payment. These rows are valid and must be kept for conversion rate calculations.

---

## ⚙️ Data Preparation & Filtering Rules

### 1. Remove non-mobile users (artifact — out of scope)
The redesign was built for **mobile only**.  
Non-mobile users who appear in both test and control groups are an artifact of the experiment assignment system and must be **excluded from all analyses**.

```python
# Keep only mobile users
df = df[df['platform'].str.lower().isin(['mobile', 'android', 'ios'])]
# OR filter by 'system' column if platform is ambiguous — inspect both columns first
```

### 2. Remove pre-experiment data
Only include users whose **registration date** (`date_reg`) is **on or after July 24** to avoid contamination from users registered before the experiment started.

```python
df = df[df['date_reg'] >= '2021-07-23']
```

### 3. Sanity Check — group balance
Verify that test and control groups are balanced on invariant metrics (metrics that should NOT be affected by the experiment):
- `gender` distribution
- `age_group` distribution
- `country_group` distribution
- `id_traffic_source` distribution

Run chi-square tests for categorical balance between groups. If groups are imbalanced, flag it in the report.

---

## 🐋 Whale Segment Analysis

In whale-model games, average metrics can be misleading. Perform a **separate analysis for whale users**.

**Whale definition:** Users in the top 5% by total payment amount (among payers only).

```python
whale_threshold = df_payers['amount'].quantile(0.95)
df['is_whale'] = df['amount'] >= whale_threshold
```

For whale users, analyze separately:
- Conversion rate (whale share in test vs. control)
- Average payment amount
- Statistical significance (use Mann-Whitney U test for amounts due to non-normality)

> ⚠️ If the redesign negatively affects whales (lower amount or conversion), this is a critical red flag even if overall conversion improves.

---

## 📊 Analysis Methodology (Based on Udacity A/B Testing Framework)

Follow this sequence:

### Step 1 — Invariant Metric Sanity Checks
Confirm the experiment setup is valid by checking that non-target metrics did not change between groups:
- Use **chi-square test** for categorical distributions (gender, age_group, country_group)
- If sanity checks fail → report the flaw and proceed with caution

### Step 2 — Define Evaluation Metrics & Minimum Detectable Effect (MDE)

**Why we decompose PPU instead of testing it directly:**
PPU (payments per user, all users) has ~97% zeros (non-payers). Mann-Whitney on zero-inflated data loses power because ranks are dominated by ties at 0. The metric also conflates two independent effects — whether users start paying and how often payers buy. Instead, decompose:

```
RPU = CR × ARPP        (descriptive identity, not a test)
PPU = CR × PPP         (conceptual decomposition)
```

Primary metrics — each tested with the appropriate method:
| Metric | Definition | Test | MDE |
|---|---|---|---|
| Conversion Rate (CR) | % of users who made ≥1 successful payment | Two-proportion Z-test | Δ ≥ 1 pp |
| Payments per Payer (PPP) | Mean payment count **among payers only** | Mann-Whitney U | Δ ≥ 10% |
| ARPP | Mean `amount` among payers | Mann-Whitney U | Δ ≥ 10% |

Descriptive (not tested directly):
- **RPU** = total revenue / all users = CR × ARPP. Reported as a number, no significance badge.
- **Total Revenue** — reported as absolute sum with bootstrap CI.

Secondary metrics (whale-specific):
- Whale share among payers
- Whale average payment amount
- Whale RPU (whale revenue / all users)

**Why not multi-arm bandit?**
MAB is a prospective experimental design (routes traffic dynamically during the experiment). It cannot be applied retroactively to fixed-split historical data. Additionally, in a whale model the reward signal is delayed and highly variable — early whale payments create noisy signals that cause MAB to prematurely exploit a suboptimal variant.

### Step 3 — Statistical Tests

**For Conversion Rate (binary outcome):**
- Use **two-proportion Z-test**, one-tailed (test > control)
- Significance level: α = 0.05, Bonferroni-corrected threshold: α/3 ≈ 0.0167

```python
from statsmodels.stats.proportion import proportions_ztest
_, pval = proportions_ztest([test_conversions, ctrl_conversions], [n_test, n_ctrl], alternative='larger')
```

**For Payments per Payer and ARPP (continuous, payers only, no zeros):**
- Use **Mann-Whitney U test** — no normality assumption, robust to whale outliers
- Bootstrap CI (10 000 iterations) for the difference in means

```python
from scipy.stats import mannwhitneyu
_, pval = mannwhitneyu(test_vals, ctrl_vals, alternative='greater')
```

**Do NOT use Mann-Whitney for RPU or raw PPU (all users)** — zero-inflation makes ranks uninformative. RPU is descriptive only.

**Compute Confidence Intervals** for the difference in conversion rates (normal approximation) and mean amounts (bootstrap).

### Step 4 — Effect Size
- For proportions: compute **Cohen's h** or raw lift (%)
- For amounts: compute **relative difference** in medians and means

### Step 5 — Double-Check with Sign Test (optional but recommended)
Aggregate data by day. For each day, mark whether test > control. Count "wins" and run a **binomial sign test**.

```python
from scipy.stats import binom_test
pval = binom_test(wins, n_days, p=0.5, alternative='greater')
```

### Step 6 — Segment Deep-Dives
Run conversion rate comparison for sub-segments:
- By `country_group`
- By `age_group`
- By `id_traffic_source`
- Whale vs. non-whale

Identify if there are segments where the new design harms performance (heterogeneous treatment effects).

---

## 📈 Required Visualizations

All charts must have clear titles, axis labels, and a text annotation explaining what the chart shows in plain language.

1. **Bar chart:** Conversion rate — test vs. control (with confidence intervals)
2. **Box plot / violin plot:** Payment amount distribution — test vs. control (log scale recommended for whale data)
3. **Time series:** Daily conversion rate by group (from July 24 onward)
4. **Bar chart:** Average revenue per user (ARPU) — test vs. control
5. **Heatmap or grouped bar chart:** Conversion rate by country_group × split_group
6. **Whale segment:** Side-by-side bar charts for whale CR and whale ARPP
7. **Sanity check charts:** Gender, age, country distribution by group

---

## 📝 Final Report Structure (for CEO)

The report must be self-explanatory. Structure it as follows:

Executive Summary (1 paragraph — the answer + key number)
What was tested and why (business context, no jargon)
Who was included in the analysis (filtering decisions explained)
Key Metrics Results (table + charts)
Statistical Significance Summary (plain English — "we are 95% confident that...")
Whale Impact Analysis (separate section — critical for revenue)
Segment Analysis (any notable differences by country/age)
Risks & Caveats (what we cannot conclude, experiment limitations)
Recommendation: LAUNCH / DO NOT LAUNCH / LAUNCH WITH CONDITIONS
— Include conditions if applicable (e.g., "launch only for users in Group A countries")


---

## 🗂️ Project File Structure
project/
├── CLAUDE.md               ← this file
├── raw_data.csv            ← source data
├── analysis.ipynb          ← main analysis notebook (Jupyter)
├── report.html             ← final CEO report (auto-generated from notebook)
├── charts/                 ← all saved charts (PNG, 300 DPI)
│   ├── 01_conversion_rate.png
│   ├── 02_amount_distribution.png
│   ├── 03_daily_timeseries.png
│   ├── 04_arpu.png
│   ├── 05_country_heatmap.png
│   ├── 06_whale_analysis.png
│   └── 07_sanity_checks.png
└── requirements.txt        ← pandas, scipy, statsmodels, matplotlib, seaborn, plotly

---

## ✅ Definition of Done

- [ ] Non-mobile users excluded and documented
- [ ] Pre-experiment users excluded and documented  
- [ ] Sanity checks passed (or flagged with explanation)
- [ ] Primary metrics tested with correct statistical tests
- [ ] Whale segment analyzed separately
- [ ] All 7 charts generated and saved
- [ ] p-values, confidence intervals, and effect sizes computed for all metrics
- [ ] Final report rendered as HTML (or PDF) with no code visible
- [ ] Recommendation stated clearly in first paragraph of report

---

# Behavioral Guidelines (Andrej Karpathy)

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.