"""AA check: pre-existing cohort behaviour before vs after TEST_START."""

import os
import numpy as np
import pandas as pd

from constants import (
    TEST_START,
    SCRIPT_DIR,
    load_mobile_payments,
    pre_existing_ids,
    cohort_metrics,
    user_table,
)

df = load_mobile_payments()
pre_ids = pre_existing_ids(df)
users = user_table(df)
pre_existing = users[users["date_reg"] < TEST_START].copy()

print("=== Step 2: AA Check (users registered BEFORE test start) ===")
print(f"Test start (boundary): {TEST_START}")
print(f"Pre-existing cohort (mobile, registered before test): {len(pre_existing):,} users")

# --- Artifact check ---
print("\n--- Split-group artifact check (pre-test registrants) ---")
split_counts = pre_existing["split_group"].value_counts().sort_index()
for group, count in split_counts.items():
    print(f"  split_group {group}: {count:,} users")

test_artifacts = pre_existing[pre_existing["split_group"] == 1]
if len(test_artifacts) > 0:
    print(
        f"WARN: {len(test_artifacts)} pre-test users in split_group=1 "
        "(technical artifact — do not use for A/B assignment inference)"
    )
    print(
        f"  Registration range: {test_artifacts['date_reg'].min()} "
        f"to {test_artifacts['date_reg'].max()}"
    )
else:
    print("PASS: No pre-test registrants in test group (split_group=1)")

# --- Temporal AA ---
print("\n--- Temporal stability (pre-existing cohort, same UI) ---")
print("Windows: payments < test start  vs  payments >= test start")

before = cohort_metrics(df, pre_ids, payment_end=TEST_START)
after = cohort_metrics(df, pre_ids, payment_start=TEST_START)


def print_metrics(label, m):
    print(f"\n{label}")
    print(f"  Cohort users: {m['cohort_users']:,}")
    print(f"  Paying users: {m['paying_users']:,}")
    print(f"  RPU: {m['rpu']:.4f}")
    print(f"  Conversion rate: {m['conversion_rate']:.4f}")
    print(f"  ARPU (payers): {m['arpu_payers']:.4f}")
    print(f"  Payments per user: {m['payments_per_user']:.4f}")


if before and after:
    print_metrics("Window: payments BEFORE test start", before)
    print_metrics("Window: payments ON/AFTER test start", after)

    rpu_shift = after["rpu"] - before["rpu"]
    conv_shift = after["conversion_rate"] - before["conversion_rate"]
    rpu_rel = (rpu_shift / before["rpu"] * 100) if before["rpu"] else np.nan
    conv_rel = (
        (conv_shift / before["conversion_rate"] * 100)
        if before["conversion_rate"]
        else np.nan
    )

    print("\nShift (after - before):")
    if not np.isnan(rpu_rel):
        print(f"  RPU: {rpu_shift:+.4f} ({rpu_rel:+.1f}% relative)")
    else:
        print(f"  RPU: {rpu_shift:+.4f}")
    if not np.isnan(conv_rel):
        print(f"  Conversion rate: {conv_shift:+.4f} ({conv_rel:+.1f}% relative)")
    else:
        print(f"  Conversion rate: {conv_shift:+.4f}")

    if abs(rpu_rel) > 20 or abs(conv_rel) > 20:
        print("WARNING: Large shift across boundary — possible external confound")
    else:
        print("PASS: Pre-existing cohort relatively stable across boundary")
else:
    print("Insufficient data to compare time windows.")

# Save user-level summary for 02b
payments_ok = df[
    df["id_user"].isin(pre_ids)
    & df["date_payment"].notna()
    & (df["successful_payment"] == 1)
]
rev_before = (
    payments_ok[payments_ok["date_payment"] < TEST_START]
    .groupby("id_user")["amount"]
    .sum()
)
rev_after = (
    payments_ok[payments_ok["date_payment"] >= TEST_START]
    .groupby("id_user")["amount"]
    .sum()
)

user_summary = pre_existing.copy()
user_summary["revenue_before"] = user_summary["id_user"].map(rev_before).fillna(0)
user_summary["revenue_after"] = user_summary["id_user"].map(rev_after).fillna(0)
user_summary["paid_before"] = user_summary["revenue_before"] > 0
user_summary["paid_after"] = user_summary["revenue_after"] > 0

output_path = os.path.join(SCRIPT_DIR, "pre_test_user_data.csv")
user_summary.to_csv(output_path, index=False)
print(f"\nPre-existing cohort user summary saved to: {output_path}")
