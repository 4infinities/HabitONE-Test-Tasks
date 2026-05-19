"""
Step 6: Power analysis for main A/B hypothesis.
Primary: payments_per_user. Secondary: RPU.
Alpha=0.05, Power=0.80, MDE=10%.
"""

import numpy as np
import os
import pandas as pd
from scipy import stats

from constants import SCRIPT_DIR, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
ALPHA = 0.05
POWER_TARGET = 0.80
MDE = 0.10                                          # reference MDE for continuous metrics
MDE_RANGE = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]  # sensitivity sweep
MDE_CR_PP = 0.01                                    # 1 pp absolute MDE for conversion rate


def required_n(mean_c, std_c, mde=MDE, alpha=ALPHA, power=POWER_TARGET):
    delta = mean_c * mde
    if delta == 0 or std_c == 0:
        return float("nan")
    z = stats.norm.ppf(1 - alpha) + stats.norm.ppf(power)  # one-tailed
    return int(np.ceil(2 * z ** 2 * std_c ** 2 / delta ** 2))


def obs_power(mean_c, std_c, n, mde=MDE, alpha=ALPHA):
    delta = mean_c * mde
    if delta == 0 or std_c == 0:
        return float("nan")
    z_a = stats.norm.ppf(1 - alpha)  # one-tailed
    ncp = (delta / std_c) * np.sqrt(n / 2)
    return float(1 - stats.norm.cdf(z_a - ncp))


def power_row(scenario, metric, ctrl, test, mde=MDE):
    mean_c, std_c = ctrl.mean(), ctrl.std(ddof=1)
    n_c, n_t = len(ctrl), len(test)
    req = required_n(mean_c, std_c, mde=mde)
    return {
        "scenario": scenario,
        "metric": metric,
        "mde_pct": mde,
        "baseline_mean": mean_c,
        "baseline_std": std_c,
        "mde_absolute": mean_c * mde,
        "required_n": req,
        "actual_n_control": n_c,
        "actual_n_test": n_t,
        "powered": (n_c >= req and n_t >= req) if not np.isnan(req) else False,
        "obs_power_at_mde": obs_power(mean_c, std_c, min(n_c, n_t), mde=mde),
        "obs_effect_pct": (test.mean() / mean_c - 1) if mean_c != 0 else float("nan"),
    }


def required_n_proportion(p_c, mde_pp=MDE_CR_PP, alpha=ALPHA, power=POWER_TARGET):
    """Sample size for two-proportion one-tailed test via Cohen's h."""
    p_t = p_c + mde_pp
    if p_t >= 1.0 or p_c <= 0:
        return float("nan")
    h = 2 * (np.arcsin(np.sqrt(p_t)) - np.arcsin(np.sqrt(p_c)))
    z = stats.norm.ppf(1 - alpha) + stats.norm.ppf(power)
    return int(np.ceil((z / h) ** 2))


def obs_power_proportion(p_c, n, mde_pp=MDE_CR_PP, alpha=ALPHA):
    p_t = p_c + mde_pp
    if p_t >= 1.0 or p_c <= 0:
        return float("nan")
    h = 2 * (np.arcsin(np.sqrt(p_t)) - np.arcsin(np.sqrt(p_c)))
    z_a = stats.norm.ppf(1 - alpha)
    ncp = h * np.sqrt(n / 2)
    return float(1 - stats.norm.cdf(z_a - ncp))


def power_row_proportion(scenario, metric, ctrl, test):
    p_c = (ctrl["revenue"] > 0).mean()
    p_t = (test["revenue"] > 0).mean()
    n_c, n_t = len(ctrl), len(test)
    req = required_n_proportion(p_c)
    return {
        "scenario": scenario,
        "metric": metric,
        "mde_pct": MDE_CR_PP,
        "baseline_mean": p_c,
        "baseline_std": float("nan"),
        "mde_absolute": MDE_CR_PP,
        "required_n": req,
        "actual_n_control": n_c,
        "actual_n_test": n_t,
        "powered": (n_c >= req and n_t >= req) if not np.isnan(req) else False,
        "obs_power_at_mde": obs_power_proportion(p_c, min(n_c, n_t)),
        "obs_effect_pct": (p_t / p_c - 1) if p_c != 0 else float("nan"),
    }


def run_scenario(df, label):
    ab = build_ab_user_revenue(df)
    ctrl, test = ab[ab["split_group"] == 0], ab[ab["split_group"] == 1]
    ctrl_arpp = ctrl[ctrl["revenue"] > 0]["revenue"]
    test_arpp = test[test["revenue"] > 0]["revenue"]
    rows = [power_row_proportion(label, "conversion_rate", ctrl, test)]
    for mde in MDE_RANGE:
        rows.append(power_row(label, "ARPP", ctrl_arpp, test_arpp, mde=mde))
        rows.append(power_row(label, "RPU", ctrl["revenue"], test["revenue"], mde=mde))
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = run_scenario(load_mobile_payments(), "mobile") + run_scenario(load_all_payments(), "all_devices")
    out = pd.DataFrame(rows)

    print("\n=== POWER ANALYSIS  (MDE=10%, alpha=0.05, power=0.80) ===")
    print(out.to_string(index=False))

    path = os.path.join(OUTPUT_DIR, "power_table.csv")
    out.to_csv(path, index=False, float_format="%.6f")
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
