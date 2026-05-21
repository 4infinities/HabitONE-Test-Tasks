"""Sample homogeneity: A/B test body (registered on or after TEST_START)."""

import os
import pandas as pd
from scipy.stats import chi2_contingency

from constants import TEST_START, SCRIPT_DIR, load_mobile_payments, ab_test_ids

RAW_DATA_PATH = os.path.join(SCRIPT_DIR, "..", "Raw Data.csv")

DIMENSIONS = ["gender", "age_group", "country_group", "id_traffic_source", "system"]
ALPHA = 0.05
BONFERRONI_ALPHA = ALPHA / len(DIMENSIONS)  # 0.01

print("=== Step 3: Sample Homogeneity (A/B test body) ===")
print(f"Test start: {TEST_START}")
print("Cohort: mobile users registered ON OR AFTER test start\n")

all_rows = []

for cohort_label in ["mobile", "all"]:
    if cohort_label == "mobile":
        df = load_mobile_payments()
        print(f"Loading mobile data from {os.path.join(SCRIPT_DIR, 'mobile_data.csv')}")
    else:
        # load raw data
        df = pd.read_csv(RAW_DATA_PATH)
        df["date_reg"] = pd.to_datetime(df["date_reg"])
        df["date_payment"] = pd.to_datetime(df["date_payment"], errors="coerce")
        print(f"Loading raw data from {RAW_DATA_PATH}")

    ab_ids = ab_test_ids(df)
    print(f"{cohort_label.upper()} cohort: {len(ab_ids):,} users")

    # One attribute row per user (first row in data)
    user_attrs = (
        df[df["id_user"].isin(ab_ids)]
        .sort_values("date_reg")
        .groupby("id_user")
        .first()
        .reset_index()[["id_user", "split_group"] + DIMENSIONS]
    )

    print(f"A/B test body: {len(user_attrs):,} users")
    print(user_attrs["split_group"].value_counts().sort_index())
    print()

    for dim in DIMENSIONS:
        sub = user_attrs[["split_group", dim]].dropna()
        if sub[dim].nunique() < 2:
            rows_append = {
                "cohort": cohort_label,
                "dimension": dim,
                "p_value": float("nan"),
                "chi2": float("nan"),
                "flag": "SKIP (single level)",
                "control_n": (user_attrs["split_group"] == 0).sum(),
                "test_n": (user_attrs["split_group"] == 1).sum(),
            }
            all_rows.append(rows_append)
            continue

        ct = pd.crosstab(sub["split_group"], sub[dim])
        chi2, p, dof, expected = chi2_contingency(ct)

        # Detect small expected cells (chi2 assumption violation)
        small_cell_note = ""
        if (expected < 5).any():
            small_cats = ct.columns[(expected < 5).any(axis=0)].tolist()
            small_counts = {cat: int(ct[cat].sum()) for cat in small_cats}
            small_cell_note = f"  [small cells: {small_counts} — chi2 unreliable for these]"

        if p < BONFERRONI_ALPHA:
            flag = f"WARN p<{BONFERRONI_ALPHA:.3f} (Bonferroni)"
        elif p < ALPHA:
            flag = f"MARGINAL p<{ALPHA} (not significant after Bonferroni)"
        else:
            flag = "OK"

        # Print frequency table
        ct_pct = ct.div(ct.sum(axis=1), axis=0).mul(100).round(1)
        ct_display = ct.copy().astype(str)
        for col in ct.columns:
            ct_display[col] = ct[col].astype(str) + " (" + ct_pct[col].astype(str) + "%)"
        ct_display.index = ct_display.index.map({0: "control", 1: "test"})
        print(f"\n{cohort_label.upper()} — {dim}  chi2={chi2:.2f}, df={dof}, p={p:.4f}  [{flag}]")
        print(ct_display.to_string())
        if small_cell_note:
            print(f"  NOTE{small_cell_note}")

        rows_append = {
            "cohort": cohort_label,
            "dimension": dim,
            "p_value": p,
            "chi2": chi2,
            "dof": dof,
            "flag": flag,
            "small_cell_note": small_cell_note.strip(),
            "control_n": (user_attrs["split_group"] == 0).sum(),
            "test_n": (user_attrs["split_group"] == 1).sum(),
        }
        all_rows.append(rows_append)

out_dir = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "homogeneity_table.csv")
pd.DataFrame(all_rows).to_csv(out_path, index=False)
print(f"\nSaved: {out_path}")

warns = [r["dimension"] for r in all_rows if r.get("flag", "").startswith("WARN")]
marginals = [r["dimension"] for r in all_rows if r.get("flag", "").startswith("MARGINAL")]
if warns:
    print(f"\nWARNING (Bonferroni p<{BONFERRONI_ALPHA:.3f}): {', '.join(warns)}")
if marginals:
    print(f"MARGINAL (p<{ALPHA} but not after Bonferroni): {', '.join(marginals)}")
if not warns and not marginals:
    print(f"\nPASS: No significant imbalance (Bonferroni-corrected α={BONFERRONI_ALPHA:.3f})")