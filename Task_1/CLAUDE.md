# A/B Test Analysis — Mobile Payment Screen Redesign

## Business Context

A game project where users buy in-game currency with real money. The design team proposed a new mobile payment screen UI to increase payment activity. The new variant was rolled out starting **July 23, 00:00** to a subset of users (`split_group = 1`), while the rest kept the baseline (`split_group = 0`).

**Key business question:** Should we roll out the new payment screen to all users, or reject it?

> **Analysis boundary:** All cohort splits and payment windows use `TEST_START = 2021-07-23 00:00:00` from `analysis/constants.py` (A/B registrations begin on this date in the data).

---

## Data Dictionary

| Field | Description |
|---|---|
| `id_user` | User identifier |
| `gender` | User gender |
| `date_reg` | Registration datetime |
| `platform` | User platform |
| `Id_traffic_source` | Ad platform / traffic source |
| `country_group` | Country group |
| `age_group` | Age group |
| `system` | Device OS |
| `date_payment` | Payment datetime (NULL = registered but never paid) |
| `method` | Payment method |
| `amount` | Payment amount |
| `successful_payment` | 1 if payment was successful |
| `split_group` | 0 = control, 1 = test |

> **Important:** Rows with NULL `date_payment` = registered users who never made a payment. They MUST be included in the denominator for conversion rate and RPU calculations.

---

## Primary Metrics

| Metric | Formula | Rationale |
|---|---|---|
| **Revenue Per User (RPU)** | `SUM(amount) / COUNT(DISTINCT id_user)` | Core business metric — not just payment count |
| **Conversion Rate** | `COUNT(DISTINCT paying users) / COUNT(DISTINCT all users)` | Secondary — funnel health |
| **ARPU among payers** | `SUM(amount) / COUNT(DISTINCT paying users)` | Whale detection component |
| **Payments per user** | `COUNT(payments) / COUNT(DISTINCT id_user)` | Proxy metric mentioned in task |

---

## Implementation Plan

### STEP 0 — Data Loading & Initial Audit

```python
# Load raw_data file
# Check shape, dtypes, nulls
# Check date ranges: date_reg, date_payment
# Verify split_group distribution (is it ~50/50?)
# Check for users appearing in both groups (contamination check)
```

**Critical checks:**
- Are there users with `split_group` that changes across rows? → flag as contaminated
- What is the actual split ratio? (may not be 50/50)
- What platforms are present? (`platform` values)

---

### STEP 1 — Data Filtering

```python
# Filter: keep only MOBILE users
# Exclude platform == 'desktop' and platform == 'other'
# BUT: first run a REFERENCE CHECK on desktop/other users:
#   - If desktop/other shows NO difference between groups → confirms randomization worked
#   - If desktop/other shows a difference → red flag (systematic bias in assignment)

# After reference check, proceed with mobile-only cohort for main analysis
```

**Rationale:** The UI change was mobile-only. Desktop/other should show zero effect — use them as a randomization sanity check.

---

### STEP 2 — AA Check (users registered BEFORE July 23)

**Cohort logic:**
- Users registered **before July 23** never saw the new screen — their UI never changed.
- Users registered **from July 23 onward** are the actual A/B test body (split_group 0 vs 1).

These are two separate populations and must never be mixed in the main analysis.

```python
# Take users registered BEFORE July 23 (pre-existing cohort)
# Compare their RPU and conversion rate in two time windows:
#   - Their behaviour BEFORE July 23
#   - Their behaviour AFTER July 23 (same screen, different calendar period)
# If metrics shift significantly after July 23 for this cohort →
#   something external changed (seasonality, promo, bug) that will
#   also affect the A/B test groups and cannot be attributed to the UI change.

# Additionally: check if any pre-July-23 users have split_group assigned.
# If yes → likely a technical artifact; exclude them from the A/B test body.
```

**What this tells us:** If the old cohort's behaviour is stable across the July 23 boundary, external conditions are clean and the A/B test result can be trusted. If it shifts — flag as a confound.

---

### STEP 2.5 — Baseline Metrics (pre July 23, mobile only)

```python
# Take all mobile users with activity BEFORE July 23
# Aggregate to id_user level
# Calculate:
#   - RPU (total revenue / all users incl. non-payers)
#   - Conversion rate (paying users / all users)
#   - ARPU among payers only
#   - Median and mean RPU, mean/median ratio
#   - Revenue distribution shape (for whale pre-check)

# This is the baseline from which MDE is expressed as a % uplift.
# After computing this, ask the user:
#   "Baseline RPU = X. What uplift % was expected from this test?
#    This is needed to calculate required sample size."
```

**Output:** Single baseline metrics table (pre-test, mobile only). This is the reference point for all subsequent comparisons and for the power analysis in Step 6.

---

### STEP 3 — Sample Homogeneity Check

For each dimension below, compare **control vs test** distributions using:
- Chi-square test for categorical variables
- Summary table with % breakdown

**Dimensions to check:**
1. `gender`
2. `platform` (after filtering — should be uniform)
3. `age_group`
4. `system` (iOS vs Android — critical, behavior differs)
5. `Id_traffic_source`
6. `country_group`
7. `method` (payment method distribution)
8. Registration date distribution (are newer users over-represented in one group?)

**Output:** Single summary table — `GROUP A vs GROUP B` with p-values per dimension. Flag any dimension with p < 0.05.

---

### STEP 4 — Successful Payment Sanity Check

```python
# Quick check: did payment SUCCESS RATE change between groups?
# successful_payment = 1 rate in control vs test
# If payment processing success rate differs → technical issue, not UX effect
```

---

### STEP 5 — Whale Distribution Analysis

```python
# Aggregate to user level: total_revenue, payment_count per user
# Plot revenue distribution (log scale histogram)
# Calculate:
#   - % of users generating top 80% of revenue (Pareto check)
#   - Gini coefficient
#   - Mean vs median RPU ratio (>3x → whale model)

# Decision logic:
# IF whale model detected:
#   → Focus on: whale count per group, whale RPU, % revenue from whales
#   → Use Mann-Whitney U test (non-parametric) for RPU comparison
#   → Consider bootstrap confidence intervals
# IF near-normal distribution:
#   → Use Welch's t-test for RPU
#   → Calculate power from underlying distribution parameters
```

---

### STEP 6 — Sample Size & Power Analysis

```python
# Required inputs:
#   - Baseline RPU (from control group, post July 23)
#   - Baseline RPU std dev
#   - Desired MDE (ask: what was the expected uplift? default assumption: 5-10%)
#   - Alpha = 0.05, Power = 0.80 (standard)
#   - Actual split ratio from data

# Calculate:
#   - Required sample size per group
#   - Actual sample size per group
#   - Are we underpowered or overpowered?

# NOTE: If MDE was never pre-specified, document this as a limitation.
# Use the OBSERVED effect size only for informational purposes, 
# not as post-hoc justification.
```

---

### STEP 7 — Statistical Tests

#### If NON-whale distribution:
```python
# Primary test: Welch's t-test on RPU (user-level aggregation)
# Secondary test: Chi-square on conversion rate
# Correction: Bonferroni for multiple metrics (RPU + conversion rate + ARPU)
```

#### If WHALE distribution:
```python
# Primary test: Mann-Whitney U on RPU
# Bootstrap CI (10,000 iterations) on mean RPU difference
# Permutation test as robustness check
# Compare: whale count per group, whale ARPU
```

**Critical:** Unit of analysis = `id_user` (not individual payments). Aggregate first, then test.

---

### STEP 8 — Temporal Stability Analysis

```python
# Split post-July 23 period into time buckets (daily or weekly)
# For each bucket: calculate RPU by group
# Plot: RPU over time, control vs test

# Look for:
#   1. Novelty effect — test group spikes early then converges → NOT a real effect
#   2. Ramp-up — effect strengthens over time → possibly real, possibly learning
#   3. Stable separation — consistent gap over time → strong evidence

# If experiment ran < 2 weeks: flag as potentially insufficient for novelty detection
```

---

### STEP 9 — Subgroup Analysis (Exploratory)

```python
# Break results by: iOS vs Android, age_group, country_group
# Purpose: identify if effect is concentrated in a specific segment
# WARNING: these are exploratory — do not use for primary decision
# Apply FDR correction if reporting multiple subgroup p-values
```

---

### STEP 10 — Final Outputs

#### Tables:
1. **Sample homogeneity table** — % breakdown by dimension, control vs test, p-value
2. **Core metrics table** — RPU, conversion rate, ARPU, payments/user — control vs test, absolute diff, relative diff, CI, p-value
3. **Power analysis table** — required n, actual n, observed effect, MDE

#### Charts:
1. **Revenue distribution** — log-scale histogram, control vs test (whale check)
2. **RPU over time** — daily/weekly line chart, control vs test (novelty/stability check)
3. **Conversion funnel** — registered → paid, by group
4. **Subgroup heatmap** — RPU lift by segment (iOS/Android × age group)

---

### STEP 11 — Conclusion Framework

Answer these questions in order:

| # | Question | Source |
|---|---|---|
| 1 | Were groups comparable before the test? | Step 2 (AA check) |
| 2 | Are groups demographically similar? | Step 3 |
| 3 | Is the sample size sufficient? | Step 6 |
| 4 | Is the effect statistically significant? | Step 7 |
| 5 | Is the effect practically significant (MDE exceeded)? | Step 7 |
| 6 | Is the effect stable over time (not novelty)? | Step 8 |
| 7 | Does the effect hold across key segments? | Step 9 |

**Decision rule:**
- ALL of 1–6 satisfied → **Roll out**
- 4 significant but 5 or 6 fails → **Extend test / inconclusive**
- 1 or 2 fails → **Experiment compromised, do not decide**
- 3 fails (underpowered) → **Cannot conclude, extend test**

---

## Critical Pitfalls to Avoid

| Pitfall | Mitigation |
|---|---|
| Analyzing payment rows instead of users | Always aggregate to `id_user` level first |
| Excluding non-payers from denominator | NULL `date_payment` rows stay in denominator |
| Ignoring novelty effect | Check temporal stability (Step 8) |
| Desktop/other contaminating mobile test | Filter before main analysis (Step 1) |
| Multiple comparisons inflation | Bonferroni or FDR correction (Step 7) |
| Post-hoc MDE justification | Document if MDE was never pre-specified |
| User contamination (both groups) | Check for duplicate `id_user` across groups (Step 0) |
| Ignoring split ratio | Verify actual ratio, adjust power calc accordingly |

---

## File Structure (expected output)

```
/analysis/
├── 00_data_audit.py
├── 01_filtering.py
├── 02_aa_check.py
├── 03_homogeneity.py
├── 04_sanity_checks.py
├── 05_whale_analysis.py
├── 06_power_analysis.py
├── 07_statistical_tests.py
├── 08_temporal_stability.py
├── 09_subgroup_analysis.py
├── 10_final_report.ipynb
└── outputs/
    ├── homogeneity_table.csv
    ├── metrics_table.csv
    ├── power_table.csv
    ├── revenue_distribution.png
    ├── rpu_over_time.png
    ├── conversion_funnel.png
    └── subgroup_heatmap.png
```

---

## Output Formats

The formats listed above (CSV tables, PNG charts, Jupyter notebook) are a starting point. **The user will specify additional or alternative output formats before implementation begins** — e.g. PDF report, HTML dashboard, Google Sheets export, Markdown summary, Notion-ready tables, etc. Do not finalize output format decisions until confirmed.

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