"""Sample homogeneity: A/B test body (registered on or after TEST_START)."""

import os
import pandas as pd
from scipy.stats import chi2_contingency

from constants import TEST_START, SCRIPT_DIR, load_mobile_payments, ab_test_ids

RAW_DATA_PATH = os.path.join(SCRIPT_DIR, "..", "Raw Data.csv")

DIMENSIONS = ["gender", "age_group", "country_group", "id_traffic_source", "system"]

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
        chi2, p, _, _ = chi2_contingency(ct)
        flag = "WARN p<0.05" if p < 0.05 else "OK"
        rows_append = {
            "cohort": cohort_label,
            "dimension": dim,
            "p_value": p,
            "chi2": chi2,
            "flag": flag,
            "control_n": (user_attrs["split_group"] == 0).sum(),
            "test_n": (user_attrs["split_group"] == 1).sum(),
        }
        all_rows.append(rows_append)
        print(f"{cohort_label} - {dim}: chi2={chi2:.2f}, p={p:.4f}  [{flag}]")

out_dir = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "homogeneity_table.csv")
pd.DataFrame(all_rows).to_csv(out_path, index=False)
print(f"\nSaved: {out_path}")

warns = [r["dimension"] for r in all_rows if r.get("flag", "").startswith("WARN")]
if warns:
    print(f"\nWARNING: Imbalance detected in: {', '.join(warns)}")
else:
    print("\nPASS: No significant imbalance (p < 0.05) across checked dimensions")