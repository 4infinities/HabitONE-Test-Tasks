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

from constants import SCRIPT_DIR, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")

# Стандартный уровень значимости: вероятность ложноположительного результата
ALPHA = 0.05

# Количество тестируемых метрик — нужно для поправки Bonferroni
N_METRICS = 3  # payments_per_user, RPU, conversion_rate

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
    _, p = stats.mannwhitneyu(ctrl, test, alternative="two-sided")
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


def chi2_row(scenario, ctrl, test):
    """
    Хи-квадрат тест для сравнения конверсии (доля плательщиков).

    Что проверяет: одинакова ли доля плательщиков в группах?
    H0: conversion_rate(ctrl) == conversion_rate(test).

    Как работает:
      - Строится таблица сопряжённости 2×2:
          [заплатили_ctrl, не заплатили_ctrl]
          [заплатили_test, не заплатили_test]
      - Сравниваются наблюдаемые частоты с ожидаемыми при H0.
      - Подходит именно здесь: бинарный исход (заплатил / нет),
        большой размер выборки (n >> 5 в каждой ячейке).
      - correction=False: поправка Йетса не нужна при больших выборках.
    """
    c_pay = int((ctrl["revenue"] > 0).sum())
    t_pay = int((test["revenue"] > 0).sum())
    table = [[c_pay, len(ctrl) - c_pay], [t_pay, len(test) - t_pay]]
    _, p = stats.chi2_contingency(table, correction=False)[:2]
    m_c, m_t = c_pay / len(ctrl), t_pay / len(test)
    return {
        "scenario": scenario,
        "metric": "conversion_rate",
        "test": "Chi-square",
        "control_mean": m_c,
        "test_mean": m_t,
        "abs_diff": m_t - m_c,
        "rel_diff_pct": (m_t / m_c - 1) * 100 if m_c else float("nan"),
        "ci_95_low": float("nan"),
        "ci_95_high": float("nan"),
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

    rows = [
        mw_row(label, "payments_per_user", ctrl["payment_count"].astype(float), test["payment_count"].astype(float)),
        mw_row(label, "RPU", ctrl["revenue"], test["revenue"]),
        chi2_row(label, ctrl, test),
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
    return pd.DataFrame(rows), whale_info


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_rows, whale_rows = [], []

    for df, label in [(load_mobile_payments(), "mobile"), (load_all_payments(), "all_devices")]:
        tests_df, whale_info = run_scenario(df, label)
        all_rows.append(tests_df)
        whale_rows.append(whale_info)

        # Скорректированный порог: 0.05 / 3 ≈ 0.0167
        print(f"\n{'='*60}")
        print(f"STATISTICAL TESTS: {label.upper()}  (Bonferroni alpha = {ALPHA/N_METRICS:.4f})")
        print(f"{'='*60}")
        print(tests_df[[
            "metric", "control_mean", "test_mean", "rel_diff_pct",
            "ci_95_low", "ci_95_high", "p_value", "p_bonferroni", "significant",
        ]].to_string(index=False))
        print(f"\n  Whale RPU (cutoff ${whale_info['whale_cutoff']:,.2f}): "
              f"ctrl=${whale_info['whale_rpu_control']:.4f}  "
              f"test=${whale_info['whale_rpu_test']:.4f}  "
              f"diff={whale_info['whale_rpu_rel_diff_pct']:+.1f}%")

    pd.concat(all_rows, ignore_index=True).to_csv(
        os.path.join(OUTPUT_DIR, "metrics_table.csv"), index=False, float_format="%.6f")
    pd.DataFrame(whale_rows).to_csv(
        os.path.join(OUTPUT_DIR, "whale_rpu_step7.csv"), index=False, float_format="%.4f")
    print(f"\nSaved: metrics_table.csv, whale_rpu_step7.csv")


if __name__ == "__main__":
    main()
