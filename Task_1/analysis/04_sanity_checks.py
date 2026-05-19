"""Sanity check: payment success rate in A/B test body (post TEST_START)."""

import os
import pandas as pd
from scipy.stats import chi2_contingency

from constants import TEST_START, SCRIPT_DIR, load_mobile_payments, ab_test_ids

print("=== Step 4: Successful Payment Sanity Check ===")
print(f"Post-test payments (date_payment >= {TEST_START}), A/B test body only\n")

df = load_mobile_payments()
ab_ids = ab_test_ids(df)

post = df[
    df["id_user"].isin(ab_ids)
    & df["date_payment"].notna()
    & (df["date_payment"] >= TEST_START)
]

# All payment attempts in window (including failed)
summary = (
    post.groupby("split_group")
    .agg(
        attempts=("successful_payment", "count"),
        successes=("successful_payment", lambda s: (s == 1).sum()),
    )
    .reset_index()
)
summary["success_rate"] = summary["successes"] / summary["attempts"]

print(summary.to_string(index=False))

ct = pd.crosstab(post["split_group"], post["successful_payment"])
chi2, p, _, _ = chi2_contingency(ct)
print(f"\nChi-square (success vs group): chi2={chi2:.4f}, p={p:.4f}")

c0 = summary.loc[summary["split_group"] == 0, "success_rate"].iloc[0]
c1 = summary.loc[summary["split_group"] == 1, "success_rate"].iloc[0]
diff = c1 - c0
print(f"Success rate diff (test - control): {diff:+.4f}")

if p < 0.05:
    print("WARN: Success rate differs between groups — possible technical issue")
else:
    print("PASS: No significant difference in payment success rate")

out_dir = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)
summary["p_value"] = p
summary.to_csv(os.path.join(out_dir, "sanity_success_rate.csv"), index=False)
print(f"\nSaved: {os.path.join(out_dir, 'sanity_success_rate.csv')}")
