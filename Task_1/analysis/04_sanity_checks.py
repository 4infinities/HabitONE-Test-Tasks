"""Sanity check: payment success rate in A/B test body (post TEST_START)."""

import os
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from constants import TEST_START, SCRIPT_DIR, load_mobile_payments, ab_test_ids

Z95 = 1.96  # z-score for 95% CI


def ci_diff(s0, n0, s1, n1):
    """95% CI (Wald) on difference of two proportions (test - control).
    Returns (diff, ci_lo, ci_hi), or NaNs if either group is empty.
    """
    if n0 == 0 or n1 == 0:
        nan = float("nan")
        return nan, nan, nan
    p0, p1 = s0 / n0, s1 / n1
    diff = p1 - p0
    se = np.sqrt(p0 * (1 - p0) / n0 + p1 * (1 - p1) / n1)
    return diff, diff - Z95 * se, diff + Z95 * se

print("=== Step 4: Successful Payment Sanity Check ===")
print(f"Post-test payments (date_payment >= {TEST_START}), A/B test body only\n")

df = load_mobile_payments()
ab_ids = ab_test_ids(df)

# User-level attributes (one row per user, taken from registration record)
user_attrs = (
    df[df["id_user"].isin(ab_ids)]
    .sort_values("date_reg")
    .groupby("id_user", as_index=False)
    .first()[["id_user", "country_group", "system"]]
)

# Payment attempts after test start
post = (
    df[
        df["id_user"].isin(ab_ids)
        & df["date_payment"].notna()
        & (df["date_payment"] >= TEST_START)
    ]
    .copy()
    # Drop payment-row-level country_group/system — use user-level instead
    .drop(columns=["country_group", "system"], errors="ignore")
    .merge(user_attrs, on="id_user", how="left")
)

# Normalise method: fill blank strings and NaN as "Unknown"
post["method"] = post["method"].fillna("Unknown").replace("", "Unknown")


def success_table(data: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Build control/test success rate table for one dimension."""
    rows = []
    for level in sorted(data[dim].dropna().unique()):
        sub = data[data[dim] == level]
        for grp, label in [(0, "control"), (1, "test")]:
            g = sub[sub["split_group"] == grp]
            rows.append({
                "level": str(level),
                "group": label,
                "attempts": len(g),
                "successes": int((g["successful_payment"] == 1).sum()),
            })

    tbl = pd.DataFrame(rows)
    tbl["success_rate"] = tbl["successes"] / tbl["attempts"].replace(0, float("nan"))

    pivot = tbl.pivot(index="level", columns="group",
                      values=["attempts", "successes", "success_rate"])
    pivot.columns = [f"{g}_{m}" for m, g in pivot.columns]
    pivot = pivot.reset_index()

    for col in ["control_attempts", "control_successes", "test_attempts", "test_successes"]:
        pivot[col] = pivot[col].fillna(0).astype(int)

    # CI and chi-square per level
    diffs, ci_los, ci_his, pvals = [], [], [], []
    for _, row in pivot.iterrows():
        d, lo, hi = ci_diff(
            row["control_successes"], row["control_attempts"],
            row["test_successes"],    row["test_attempts"],
        )
        diffs.append(d)
        ci_los.append(lo)
        ci_his.append(hi)

        sub = data[data[dim].astype(str) == str(row["level"])]
        ct = pd.crosstab(sub["split_group"], sub["successful_payment"])
        pvals.append(chi2_contingency(ct)[1] if ct.shape == (2, 2) else float("nan"))

    pivot["diff_pp"] = diffs
    pivot["ci_lo"]   = ci_los
    pivot["ci_hi"]   = ci_his
    pivot["chi2_p"]  = pvals

    return pivot[[
        "level",
        "control_attempts", "control_successes", "control_success_rate",
        "test_attempts", "test_successes", "test_success_rate",
        "diff_pp", "ci_lo", "ci_hi", "chi2_p",
    ]]


def fmt_rate(x):
    return f"{x:.1%}" if pd.notna(x) else "—"

def fmt_diff(x):
    return f"{x:+.1%}" if pd.notna(x) else "—"

def fmt_p(x):
    return f"{x:.4f}" if pd.notna(x) else "—"

def fmt_ci(lo, hi):
    if pd.isna(lo) or pd.isna(hi):
        return "—"
    return f"[{lo:+.1%}, {hi:+.1%}]"

def print_table(tab: pd.DataFrame):
    display = tab.copy()
    display["control_success_rate"] = display["control_success_rate"].map(fmt_rate)
    display["test_success_rate"]    = display["test_success_rate"].map(fmt_rate)
    display["diff_pp"]              = display["diff_pp"].map(fmt_diff)
    display["95% CI"]               = [fmt_ci(lo, hi) for lo, hi in zip(display["ci_lo"], display["ci_hi"])]
    display["chi2_p"]               = display["chi2_p"].map(fmt_p)
    print(display.drop(columns=["ci_lo", "ci_hi"]).to_string(index=False))


# ── Overall ──────────────────────────────────────────────────────────────────
overall = (
    post.groupby("split_group")
    .agg(attempts=("successful_payment", "count"),
         successes=("successful_payment", lambda s: (s == 1).sum()))
    .reset_index()
)
overall["success_rate"] = overall["successes"] / overall["attempts"]
overall["group"] = overall["split_group"].map({0: "control", 1: "test"})
print(overall[["group", "attempts", "successes", "success_rate"]].to_string(index=False))

ct_overall = pd.crosstab(post["split_group"], post["successful_payment"])
chi2_ov, p_ov, _, _ = chi2_contingency(ct_overall)
s0 = int(overall.loc[overall["split_group"] == 0, "successes"].iloc[0])
n0 = int(overall.loc[overall["split_group"] == 0, "attempts"].iloc[0])
s1 = int(overall.loc[overall["split_group"] == 1, "successes"].iloc[0])
n1 = int(overall.loc[overall["split_group"] == 1, "attempts"].iloc[0])
c0, c1 = s0 / n0, s1 / n1
diff_ov, ci_lo_ov, ci_hi_ov = ci_diff(s0, n0, s1, n1)
print(f"\nchi2={chi2_ov:.4f}, p={p_ov:.4f}  |  diff: {diff_ov:+.4f}  95% CI: {fmt_ci(ci_lo_ov, ci_hi_ov)}")
if p_ov < 0.05:
    print("WARN: Success rate differs between groups — investigate below")
else:
    print("PASS: No significant difference in payment success rate")

# ── Breakdowns ───────────────────────────────────────────────────────────────
breakdown_frames = []

for dim, label in [
    ("country_group", "Country group"),
    ("method",        "Payment method"),
    ("system",        "OS / system"),
]:
    tab = success_table(post, dim)
    tab.insert(0, "dimension", label)
    print(f"\n{'-'*60}")
    print(f"By {label}")
    print(f"{'-'*60}")
    print_table(tab.drop(columns="dimension"))
    breakdown_frames.append(tab)

# Save
out_dir = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)

overall_out = overall[["group", "attempts", "successes", "success_rate"]].copy()
overall_out["chi2"] = chi2_ov
overall_out["p_value"] = p_ov
overall_out.to_csv(os.path.join(out_dir, "sanity_success_rate.csv"), index=False)

breakdown_df = pd.concat(breakdown_frames, ignore_index=True)
breakdown_df.to_csv(
    os.path.join(out_dir, "sanity_success_rate_breakdown.csv"), index=False
)

print(f"\nSaved: {os.path.join(out_dir, 'sanity_success_rate.csv')}")
print(f"Saved: {os.path.join(out_dir, 'sanity_success_rate_breakdown.csv')}")
