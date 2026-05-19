"""Baseline metrics: mobile pre-existing cohort, activity before TEST_START."""

import os
import pandas as pd

from constants import (
    TEST_START,
    SCRIPT_DIR,
    load_mobile_payments,
    pre_existing_ids,
    cohort_metrics,
)

print("=== Step 2.5: Baseline Metrics (mobile, pre-test window) ===")
print(f"Test start: {TEST_START}")
print("Cohort: users registered BEFORE test start")
print(f"Payment window: date_payment < {TEST_START}\n")

df = load_mobile_payments()
cohort = pre_existing_ids(df)
metrics = cohort_metrics(df, cohort, payment_end=TEST_START)

if not metrics:
    print("ERROR: empty cohort")
    exit(1)

print(f"Cohort users: {metrics['cohort_users']:,}")
print(f"Paying users: {metrics['paying_users']:,}")
print(f"Conversion rate: {metrics['conversion_rate']:.4f}")
print(f"RPU (all users): {metrics['rpu']:.4f}")
print(f"ARPU (payers only): {metrics['arpu_payers']:.4f}")
print(f"Payments per user: {metrics['payments_per_user']:.4f}")

# User-level stats for power / whale context
payments = df[
    df["id_user"].isin(cohort)
    & df["date_payment"].notna()
    & (df["successful_payment"] == 1)
    & (df["date_payment"] < TEST_START)
]
user_rev = payments.groupby("id_user")["amount"].sum()
all_users = pd.DataFrame({"id_user": list(cohort)})
all_users["revenue"] = all_users["id_user"].map(user_rev).fillna(0)
mean_rpu = all_users["revenue"].mean()
median_rpu = all_users["revenue"].median()
ratio = mean_rpu / median_rpu if median_rpu > 0 else float("inf")
print(f"\nUser-level RPU: mean={mean_rpu:.4f}, median={median_rpu:.4f}, mean/median={ratio:.2f}x")

out_dir = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)
row = {"period": "pre_test_mobile_pre_existing", "test_start": str(TEST_START), **metrics}
row["mean_rpu"] = mean_rpu
row["median_rpu"] = median_rpu
row["mean_median_ratio"] = ratio
pd.DataFrame([row]).to_csv(os.path.join(out_dir, "baseline_metrics.csv"), index=False)
print(f"\nSaved: {os.path.join(out_dir, 'baseline_metrics.csv')}")
print("\nNote: Use baseline RPU when specifying MDE % for Step 6 (power analysis).")
