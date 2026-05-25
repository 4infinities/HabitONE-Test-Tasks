"""
Step 7: Statistical tests for main A/B hypothesis.

Почему именно эти тесты?
  - Распределение выручки — whale-модель (Gini ≈ 0.993, median RPU = 0).
    Это значит, что t-test неприменим: он предполагает нормальность,
    а у нас 97% пользователей платят 0, и единицы платят тысячи долларов.
  - Mann-Whitney U — непараметрический тест: не требует нормальности,
    работает с любым распределением, сравнивает ранги (не средние).
  - Bootstrap CI — оценка доверительного интервала для разницы средних
    через многократную случайную выборку из реальных данных.
  - Chi-square — для конверсии (бинарный исход: заплатил / не заплатил).
  - Bonferroni — поправка на множественные сравнения: мы тестируем 3 метрики,
    значит порог значимости делится на 3, чтобы не поймать ложный сигнал.
"""

import numpy as np
import os
import pandas as pd
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

from constants import SCRIPT_DIR, TEST_START, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")

# Стандартный уровень значимости: вероятность ложноположительного результата
ALPHA = 0.05

# Количество тестируемых метрик — нужно для поправки Bonferroni
# CR (Z-test) + payments_per_payer (MW) + ARPP (MW)
# RPU не тестируется напрямую — интерпретируется как CR × ARPP
N_METRICS = 3

# Число итераций bootstrap: чем больше — тем точнее CI, 10k — стандарт
N_BOOTSTRAP = 10_000

# Порог для whale: топ-пользователи, генерирующие 75% выручки среди плательщиков
WHALE_PCT = 0.75

# Фиксированный seed для воспроизводимости результатов bootstrap
RNG = np.random.default_rng(42)


def bootstrap_ci(a, b):
    """
    Bootstrap доверительный интервал (95%) для разницы средних: mean(b) - mean(a).

    Как работает:
      1. N_BOOTSTRAP раз случайно сэмплируем группы a и b с возвратом (размер = исходный).
      2. Каждый раз считаем разницу средних.
      3. Берём 2.5-й и 97.5-й перцентиль — это и есть 95% CI.

    Если CI не пересекает 0 → разница статистически значима на уровне 5%.
    Преимущество над формульным CI: не предполагает нормальность распределения.
    """
    diffs = (RNG.choice(b, (N_BOOTSTRAP, len(b)), replace=True).mean(1)
             - RNG.choice(a, (N_BOOTSTRAP, len(a)), replace=True).mean(1))
    return tuple(np.percentile(diffs, [2.5, 97.5]))


def whale_cutoff(ab):
    """
    Минимальная выручка, при которой пользователь считается whale.
    Whale-порог: наименьшая выручка среди топ-пользователей,
    суммарно дающих WHALE_PCT (75%) всей выручки плательщиков.
    """
    rev = ab[ab["revenue"] > 0]["revenue"].sort_values(ascending=False).values
    idx = int((rev.cumsum() < WHALE_PCT * rev.sum()).sum())
    return float(rev[min(idx, len(rev) - 1)])


def ttest_row(scenario, metric, ctrl, test):
    """
    Welch's t-test (two-sample, one-tailed) для сравнения средних.
    H0: mean(test) <= mean(ctrl). H1: mean(test) > mean(ctrl).
    Welch вариант (equal_var=False) не требует равенства дисперсий.
    CI считается через bootstrap — те же 10k итераций, что и у MW.
    """
    _, p = stats.ttest_ind(test, ctrl, equal_var=False, alternative="greater")
    ci = bootstrap_ci(ctrl.values, test.values)
    m_c, m_t = ctrl.mean(), test.mean()
    return {
        "scenario": scenario,
        "metric": metric,
        "test": "Welch t-test",
        "control_mean": m_c,
        "test_mean": m_t,
        "abs_diff": m_t - m_c,
        "rel_diff_pct": (m_t / m_c - 1) * 100 if m_c else float("nan"),
        "ci_95_low": ci[0],
        "ci_95_high": ci[1],
        "p_value": p,
        "p_bonferroni": min(p * N_METRICS, 1.0),
        "significant": p < ALPHA / N_METRICS,
    }


def mw_row(scenario, metric, ctrl, test):
    """
    Mann-Whitney U тест для сравнения двух независимых выборок.

    Что проверяет: отличается ли распределение метрики в группах?
    H0 (нулевая гипотеза): распределения одинаковы (нет эффекта от теста).
    H1 (альтернативная): распределения различаются (есть эффект).

    Как работает:
      - Все значения из обеих групп ранжируются вместе (1, 2, 3...).
      - Считается: насколько часто значение из группы test > значения из ctrl?
      - Если тест не влияет → вероятность этого ≈ 50%.
      - p-value: вероятность получить такой или более экстремальный результат,
        если H0 верна (т.е. эффекта нет).
      - p < alpha_bonferroni → отвергаем H0, эффект статистически значим.

    Преимущество перед t-test: работает при любом распределении,
    устойчив к выбросам (китам).
    """
    _, p = stats.mannwhitneyu(ctrl, test, alternative="greater")
    ci = bootstrap_ci(ctrl.values, test.values)
    m_c, m_t = ctrl.mean(), test.mean()
    return {
        "scenario": scenario,
        "metric": metric,
        "test": "Mann-Whitney U",
        "control_mean": m_c,
        "test_mean": m_t,
        "abs_diff": m_t - m_c,
        # Относительное изменение: насколько % test отличается от control
        "rel_diff_pct": (m_t / m_c - 1) * 100 if m_c else float("nan"),
        # Bootstrap CI для разницы средних: если [low, high] не включает 0 → значимо
        "ci_95_low": ci[0],
        "ci_95_high": ci[1],
        "p_value": p,
        # p после поправки Bonferroni: p * N_METRICS (консервативная корректировка)
        "p_bonferroni": min(p * N_METRICS, 1.0),
        # Значим ли результат с учётом поправки: p < 0.05 / 3 ≈ 0.0167
        "significant": p < ALPHA / N_METRICS,
    }



def ztest_row(scenario, ctrl, test):
    """
    Two-proportion one-tailed Z-test для conversion rate.
    H0: CR(test) <= CR(ctrl). H1: CR(test) > CR(ctrl).
    CI считается через нормальное приближение для разницы пропорций.
    """
    n_c, n_t = len(ctrl), len(test)
    conv_c = int((ctrl["payment_count"] > 0).sum())
    conv_t = int((test["payment_count"] > 0).sum())
    p_c, p_t = conv_c / n_c, conv_t / n_t
    _, p = proportions_ztest([conv_t, conv_c], [n_t, n_c], alternative="larger")
    # CI для разницы пропорций (нормальное приближение)
    se = np.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    diff = p_t - p_c
    ci_low, ci_high = diff - 1.96 * se, diff + 1.96 * se
    return {
        "scenario": scenario,
        "metric": "conversion_rate",
        "test": "Z-test (proportions)",
        "control_mean": p_c,
        "test_mean": p_t,
        "abs_diff": diff,
        "rel_diff_pct": (p_t / p_c - 1) * 100 if p_c else float("nan"),
        "ci_95_low": ci_low,
        "ci_95_high": ci_high,
        "p_value": p,
        "p_bonferroni": min(p * N_METRICS, 1.0),
        "significant": p < ALPHA / N_METRICS,
    }


def run_scenario(df, label):
    """
    Запускает все тесты для одного сценария (mobile или all_devices).
    Возвращает таблицу метрик и отдельно whale RPU сводку.
    """
    ab = build_ab_user_revenue(df)
    ctrl, test = ab[ab["split_group"] == 0], ab[ab["split_group"] == 1]

    ctrl_arpp = ctrl[ctrl["revenue"] > 0]["revenue"]
    test_arpp = test[test["revenue"] > 0]["revenue"]
    # payments_per_payer: среди плательщиков, без нулей — нет проблемы zero-inflation
    ctrl_ppp = ctrl[ctrl["payment_count"] > 0]["payment_count"]
    test_ppp = test[test["payment_count"] > 0]["payment_count"]

    rows = [
        ztest_row(label, ctrl, test),
        mw_row(label, "payments_per_payer", ctrl_ppp, test_ppp),
        mw_row(label, "ARPP", ctrl_arpp, test_arpp),
    ]

    # RPU дескриптивно: CR × ARPP, без отдельного теста
    rpu_ctrl = ctrl["revenue"].mean()
    rpu_test = test["revenue"].mean()
    rpu_info = {
        "scenario": label,
        "rpu_control": rpu_ctrl,
        "rpu_test": rpu_test,
        "rpu_rel_diff_pct": (rpu_test / rpu_ctrl - 1) * 100 if rpu_ctrl else float("nan"),
    }

    ttest_rows = [
        ttest_row(label, "payments_per_payer", ctrl_ppp, test_ppp),
        ttest_row(label, "ARPP", ctrl_arpp, test_arpp),
    ]

    # Whale RPU: выручка от китов / все пользователи группы
    # Показывает, изменилось ли поведение самых ценных пользователей
    cutoff = whale_cutoff(ab)
    w_ctrl = ctrl[ctrl["revenue"] >= cutoff]["revenue"]
    w_test = test[test["revenue"] >= cutoff]["revenue"]
    whale_rpu_c = w_ctrl.sum() / len(ctrl)
    whale_rpu_t = w_test.sum() / len(test)
    whale_info = {
        "scenario": label,
        "whale_cutoff": cutoff,
        "n_control": len(ctrl),
        "n_test": len(test),
        "whales_control": len(w_ctrl),
        "whales_test": len(w_test),
        "whale_rpu_control": whale_rpu_c,
        "whale_rpu_test": whale_rpu_t,
        "whale_rpu_rel_diff_pct": (whale_rpu_t / whale_rpu_c - 1) * 100 if whale_rpu_c else float("nan"),
    }
    comparison = _build_comparison(pd.DataFrame(rows), pd.DataFrame(ttest_rows))
    return pd.DataFrame(rows), whale_info, rpu_info, comparison


def _build_comparison(mw_df, tt_df):
    """
    Склеивает MW и t-test результаты в одну сравнительную таблицу.
    Только непрерывные метрики (без conversion_rate — там Z-test).
    Колонки: metric, p_mw, sig_mw, p_ttest, sig_ttest, verdict.
    verdict = 'AGREE' если оба теста дают одинаковый вывод о значимости.
    """
    cols = ["metric", "p_value", "p_bonferroni", "significant"]
    mw = mw_df[mw_df["metric"] != "conversion_rate"][cols].rename(
        columns={"p_value": "p_mw", "p_bonferroni": "p_bonf_mw", "significant": "sig_mw"}
    )
    tt = tt_df[cols].rename(
        columns={"p_value": "p_ttest", "p_bonferroni": "p_bonf_ttest", "significant": "sig_ttest"}
    )
    cmp = mw.merge(tt, on="metric")
    cmp["verdict"] = cmp.apply(
        lambda r: "AGREE" if r["sig_mw"] == r["sig_ttest"] else "DISAGREE", axis=1
    )
    return cmp


def sign_test(df, label):
    """
    Биномиальный знаковый тест (CLAUDE.md Step 5).
    Для каждого дня проверяем: CR(test) > CR(ctrl)?
    H0: P(test wins) = 0.5. H1: P(test wins) > 0.5.
    """
    from scipy.stats import binomtest
    ab = build_ab_user_revenue(df)
    group_n = ab.groupby("split_group")["id_user"].count()
    n_ctrl = int(group_n.get(0, 0))
    n_test = int(group_n.get(1, 0))
    if n_ctrl == 0 or n_test == 0:
        return None

    post = df[
        df["id_user"].isin(set(ab["id_user"]))
        & df["date_payment"].notna()
        & (df["date_payment"] >= TEST_START)
        & (df["successful_payment"] == 1)
    ].copy()
    post["date"] = post["date_payment"].dt.date

    # PPU sign test: daily payment count per cohort size (split_group already in post)
    daily = (
        post.groupby(["date", "split_group"])
        .size()
        .unstack(fill_value=0)
    )
    if 0 not in daily.columns or 1 not in daily.columns:
        return None
    daily = daily.rename(columns={0: "ctrl", 1: "test"})
    daily["ppu_ctrl"] = daily["ctrl"] / n_ctrl
    daily["ppu_test"] = daily["test"] / n_test

    wins = int((daily["ppu_test"] > daily["ppu_ctrl"]).sum())
    n_days = len(daily)
    result = binomtest(wins, n_days, p=0.5, alternative="greater")
    return {
        "scenario": label,
        "wins": wins,
        "n_days": n_days,
        "p_value": result.pvalue,
        "significant": result.pvalue < ALPHA,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_rows, whale_rows = [], []

    cmp_rows = []
    rpu_rows = []
    for df, label in [(load_mobile_payments(), "mobile"), (load_all_payments(), "all_devices")]:
        tests_df, whale_info, rpu_info, cmp = run_scenario(df, label)
        all_rows.append(tests_df)
        whale_rows.append(whale_info)
        rpu_rows.append(rpu_info)
        cmp["scenario"] = label
        cmp_rows.append(cmp)

        print(f"\n{'='*60}")
        print(f"STATISTICAL TESTS: {label.upper()}  (Bonferroni alpha = {ALPHA/N_METRICS:.4f})")
        print(f"Decomposition: CR (Z-test) + payments_per_payer (MW) + ARPP (MW)")
        print(f"{'='*60}")
        print(tests_df[[
            "metric", "control_mean", "test_mean", "rel_diff_pct",
            "ci_95_low", "ci_95_high", "p_value", "p_bonferroni", "significant",
        ]].to_string(index=False))
        print(f"\n  RPU (descriptive, CR * ARPP): "
              f"ctrl=${rpu_info['rpu_control']:.4f}  "
              f"test=${rpu_info['rpu_test']:.4f}  "
              f"diff={rpu_info['rpu_rel_diff_pct']:+.1f}%")

        print(f"\n--- Mann-Whitney U vs Welch t-test ({label}) ---")
        print(cmp[["metric", "p_mw", "sig_mw", "p_ttest", "sig_ttest", "verdict"]].to_string(index=False))
        print(f"\n  Whale RPU (cutoff ${whale_info['whale_cutoff']:,.2f}): "
              f"ctrl=${whale_info['whale_rpu_control']:.4f}  "
              f"test=${whale_info['whale_rpu_test']:.4f}  "
              f"diff={whale_info['whale_rpu_rel_diff_pct']:+.1f}%")

    pd.concat(all_rows, ignore_index=True).to_csv(
        os.path.join(OUTPUT_DIR, "metrics_table.csv"), index=False, float_format="%.6f")
    pd.DataFrame(whale_rows).to_csv(
        os.path.join(OUTPUT_DIR, "whale_rpu_step7.csv"), index=False, float_format="%.4f")
    pd.concat(cmp_rows, ignore_index=True).to_csv(
        os.path.join(OUTPUT_DIR, "mw_vs_ttest.csv"), index=False, float_format="%.6f")
    pd.DataFrame(rpu_rows).to_csv(
        os.path.join(OUTPUT_DIR, "rpu_descriptive.csv"), index=False, float_format="%.4f")
    print(f"\nSaved: metrics_table.csv, whale_rpu_step7.csv, mw_vs_ttest.csv, rpu_descriptive.csv")

    # Sign test — mobile only (primary scenario, CLAUDE.md Step 5)
    sign = sign_test(load_mobile_payments(), "mobile")
    if sign:
        print(f"\n--- Sign test PPU (mobile): {sign['wins']}/{sign['n_days']} days test > control"
              f"  p={sign['p_value']:.4f}  {'SIGNIFICANT' if sign['significant'] else 'not significant'}")
        pd.DataFrame([sign]).to_csv(
            os.path.join(OUTPUT_DIR, "sign_test.csv"), index=False, float_format="%.6f")
        print(f"Saved: sign_test.csv")


if __name__ == "__main__":
    main()
