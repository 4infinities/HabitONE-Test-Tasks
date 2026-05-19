# Analysis Context and Progress Tracking

## Project Overview
This document tracks the progress of the A/B test analysis for the mobile payment screen redesign. It records what has been completed, key findings, and numerical results.

## Last Updated
2026-05-19

## Important Clarification on Date Boundaries

**Single project boundary:** `TEST_START = 2021-07-23 00:00:00` in `analysis/constants.py`.

| Label | Rule |
|-------|------|
| До 23 июля (payments) | `date_payment` **<** 2021-07-23 |
| С 23 июля включительно (payments) | `date_payment` **>=** 2021-07-23 |
| Pre-existing cohort | `date_reg` **<** 2021-07-23 |
| A/B test body | `date_reg` **>=** 2021-07-23 |

A/B registrations in the data begin on 23 July; all scripts and docs use this date, not 24 July.

## Completed Steps

### Step 0 — Data Loading & Initial Audit
**Status:** Completed
**File:** `analysis/00_data_audit.py`
**Key Findings:**
- Dataset shape: (58938, 13)
- Date range for registration: 2021-06-22 00:00:34 to 2021-08-21 11:07:38
- Date range for payment: 2021-06-22 00:17:19 to 2021-08-21 10:02:55 (excluding NaT)
- Number of NaT (missing) in date_payment: 48700
- Split group distribution: 0: 49255, 1: 9683 (Proportion: 0: 0.835709, 1: 0.164291)
- Number of users appearing in both groups (contamination): 0

### Step 1 — Data Filtering
**Status:** Completed
**File:** `analysis/01_filtering.py`
**Key Findings:**
- Original dataset: 58,938 rows
- Reference check: desktop/other, registered **>= 2021-07-23** (`TEST_START`)
- Mobile users: 46,619 rows (79.1%) → `analysis/mobile_data.csv`
- Raw row-level split is ~86/14, but **A/B body** (registered >= Jul 23) is ~50/50 — see cohort table below

### Step 2 — AA Check (Pre-Existing Cohort)
**Status:** Completed
**File:** `analysis/02_aa_check.py` (+ shared `analysis/constants.py`)
**Cohort:** 28,484 mobile users registered **before** 2021-07-23

| Window | RPU | Conversion |
|--------|-----|------------|
| Payments **<** Jul 23 | 10.98 | 2.15% |
| Payments **>=** Jul 23 | 9.17 | 0.66% |

- Shift: RPU **-16.4%**, conversion **-69.2%** → **WARNING: possible external confound**
- Caveat: post-window is shorter (~3 weeks vs ~1 month pre); interpret with care
- **PASS:** no pre-test registrants with `split_group=1` (Jul 23 cohort is in A/B body)
- Output: `analysis/pre_test_user_data.csv`

### Step 2b — Pre-Test Revenue Distribution (Whale Pre-Check)
**Status:** Completed
**File:** `analysis/02b_pre_test_revenue_dist.py`
**Input:** `analysis/pre_test_user_data.csv` (pre-existing cohort, payers only)
**Output:** `analysis/outputs/pre_test_revenue_distribution.png`

**Cohort (payers only):** 28,484 users → 698 payers (2.5%)

| Metric | Mean | Median | Max | Mean/Median |
|---|---|---|---|---|
| `revenue_before` | 447.95 | 47.38 | 20,912.67 | **9.5×** |
| `revenue_after` (all payers) | 374.40 | 0.00 | 29,120.93 | — |
| `total_revenue` | 822.34 | 144.46 | 47,414.29 | **5.7×** |

**Pareto (total_revenue, n=698 payers, total=573,993.62):**
- Top 1% users (7) → **29.9%** revenue
- Top 5% users (35) → **61.7%** revenue
- **80% revenue from top 89 users (12.8% of payers)**

**Verdict — Whale model: YES (китовая модель)**
- Mean/median ratio **5.7×** on `total_revenue` (threshold in plan: >3× → whale)
- Strong Pareto concentration: top ~13% of payers drive 80% of revenue; top 1% ≈ 30%
- **Implication for Step 7:** use non-parametric tests (Mann-Whitney U), bootstrap CI; track whale count and whale ARPU per group, not only mean RPU

### Step 2.5 — Baseline Metrics
**Status:** Completed
**File:** `analysis/02_5_baseline.py`
**Output:** `analysis/outputs/baseline_metrics.csv`

Pre-existing cohort, payments **<** Jul 23:
- **Baseline RPU = 10.98** (conversion 2.15%, ARPU payers 510.06)
- Use this for MDE % in Step 6

### Step 3 — Sample Homogeneity
**Status:** Completed
**File:** `analysis/03_homogeneity.py`
**Output:** `analysis/outputs/homogeneity_table.csv`
**Cohort:** A/B body 12,031 users (control 6,070 / test 5,961)

| Dimension | p-value | Flag |
|-----------|---------|------|
| gender | 0.55 | OK |
| age_group | 0.022 | **WARN** |
| system (iOS/Android) | 0.004 | **WARN** |
| id_traffic_source | 0.30 | OK |
| country_group | 0.0004 | **WARN** |
| method | 0.093 | OK |
| reg_date (daily) | ~0 | **WARN** |

→ Groups are **not fully comparable** on demographics; stratify or adjust in interpretation.

### Step 4 — Payment Success Sanity
**Status:** Completed
**File:** `analysis/04_sanity_checks.py`
**Output:** `analysis/outputs/sanity_success_rate.csv`

Post-test payment attempts (A/B body):
- Control success rate: **61.3%**
- Test success rate: **70.4%** (diff +8.9 pp, **p < 0.001**)

→ **WARN:** technical / funnel difference, not pure UX on revenue — must discuss in conclusion.

---

## Cohort Definitions (use everywhere)

| Cohort | Rule | N users |
|--------|------|---------|
| Pre-existing | mobile, `date_reg` < 2021-07-23 | 28,484 |
| **A/B test body** | mobile, `date_reg` >= 2021-07-23 | 12,031 |
| Post-test window | `date_payment` >= 2021-07-23 | — |

Shared config: `analysis/constants.py` (`TEST_START = 2021-07-23`).

---

## Roadmap — Remaining Steps

### Phase D — Main effect (next to build)

| Step | File | Purpose | Notes |
|------|------|---------|-------|
| **5** | `05_whale_analysis.py` | Pareto/Gini/whales **by group**, post-test | Pre-check done (2b); compare whale count & ARPU control vs test |
| **6** | `06_power_analysis.py` | Required vs actual n | Baseline RPU=10.98; split ~50/50; **need MDE % from user** |
| **7** | `07_statistical_tests.py` | Primary inference | **Whale path:** Mann-Whitney, bootstrap CI, whale metrics; Bonferroni |
| **8** | `08_temporal_stability.py` | RPU over time by group | Novelty / stability |
| **9** | `09_subgroup_analysis.py` | iOS/Android, age, country | Exploratory + FDR |

### Phase E — Deliverable

| Step | File | Purpose |
|------|------|---------|
| **10** | `10_final_report.ipynb` | Tables + charts from `outputs/` |
| **11** | (in report) | Decision matrix per CLAUDE.md Step 11 |

### Known risks for conclusion (already flagged)

1. **AA temporal shift** (-16.4% RPU) — external confound possible
2. **Homogeneity** — age, system, country, reg date imbalanced
3. **Success rate** — test higher; revenue lift may mix UX + processing
4. **Whale model** — non-parametric tests mandatory
5. **Unequal calendar windows** in AA — document in report

---

## Results Summary (running)

| Check | Result |
|-------|--------|
| Whale model | **YES** (mean/median 5.7×) |
| AA stability | **FAIL / WARN** |
| Homogeneity | **WARN** (4 dimensions) |
| Success rate sanity | **WARN** (test +8.9 pp) |
| Primary A/B effect | *pending Step 7* |

## Next Actions (build order)

1. `05_whale_analysis.py` — post-test, by split_group
2. `06_power_analysis.py` — ask user for expected uplift % (default 5–10% sensitivity)
3. `07_statistical_tests.py` — whale-aware primary metrics
4. `08_temporal_stability.py` → `09_subgroup_analysis.py` → `10_final_report.ipynb`