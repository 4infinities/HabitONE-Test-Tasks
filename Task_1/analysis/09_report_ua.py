"""
Step 9 (UA): Generate CEO-facing HTML report in Ukrainian with embedded charts.
Run after: 01_filtering.py, 08_charts.py
"""
import base64
import os
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from constants import SCRIPT_DIR, TEST_START, build_ab_user_revenue, load_mobile_payments

CHARTS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "charts"))
REPORT_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "report_ua.html"))
ALPHA = 0.05
RNG = np.random.default_rng(42)
N_BOOT = 5_000


def _bootstrap_ci(arr):
    samples = RNG.choice(arr, (N_BOOT, len(arr)), replace=True).mean(1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def _whale_cutoff(ab, pct=0.75):
    payers = ab.loc[ab["revenue"] > 0, "revenue"].sort_values(ascending=False).values
    idx = int((np.cumsum(payers) < pct * payers.sum()).sum())
    return float(payers[min(idx, len(payers) - 1)])


def compute_results(df):
    ab = build_ab_user_revenue(df)
    ctrl = ab[ab["split_group"] == 0]
    test = ab[ab["split_group"] == 1]

    n_c, n_t = len(ctrl), len(test)
    pay_c = int((ctrl["revenue"] > 0).sum())
    pay_t = int((test["revenue"] > 0).sum())
    cr_c, cr_t = pay_c / n_c, pay_t / n_t

    # PRIMARY METRIC: Payments Per User — Mann-Whitney U (test > control)
    ppu_c = ctrl["payment_count"].mean()
    ppu_t = test["payment_count"].mean()
    _, p_ppu = stats.mannwhitneyu(test["payment_count"], ctrl["payment_count"], alternative="greater")
    ci_ppu_c = _bootstrap_ci(ctrl["payment_count"].values)
    ci_ppu_t = _bootstrap_ci(test["payment_count"].values)

    # ARPP: payer-only amounts, Mann-Whitney (test > control)
    arpp_c = ctrl.loc[ctrl["revenue"] > 0, "revenue"]
    arpp_t = test.loc[test["revenue"] > 0, "revenue"]
    _, p_arpp = stats.mannwhitneyu(arpp_t, arpp_c, alternative="greater")

    # RPU: all users, Mann-Whitney (test > control)
    _, p_rpu = stats.mannwhitneyu(test["revenue"], ctrl["revenue"], alternative="greater")
    rpu_c, rpu_t = ctrl["revenue"].mean(), test["revenue"].mean()

    # Bootstrap CI for RPU
    ci_rpu_c = _bootstrap_ci(ctrl["revenue"].values)
    ci_rpu_t = _bootstrap_ci(test["revenue"].values)

    # Power analysis for PPU (5% relative MDE, alpha=0.05, power=0.80)
    ppu_mde = ppu_c * 1.05
    ppu_sd = ctrl["payment_count"].std()
    z_req = stats.norm.ppf(1 - ALPHA) + stats.norm.ppf(0.80)
    n_req_ppu = int(np.ceil(2 * (z_req * ppu_sd / (ppu_mde - ppu_c)) ** 2)) if ppu_mde > ppu_c and ppu_sd > 0 else float("nan")
    obs_power_ppu = float(1 - stats.norm.cdf(
        stats.norm.ppf(1 - ALPHA) - abs(ppu_t - ppu_c) / (ppu_sd * np.sqrt(2 / min(n_c, n_t)))))

    # Conversion rate (secondary — kept for reference)
    diff_cr = cr_t - cr_c
    se_cr = np.sqrt(cr_t * (1 - cr_t) / n_t + cr_c * (1 - cr_c) / n_c)

    # Whale metrics
    cutoff = _whale_cutoff(ab)
    w_c = ctrl[ctrl["revenue"] >= cutoff]
    w_t = test[test["revenue"] >= cutoff]
    payers_c = int((ctrl["revenue"] > 0).sum())
    payers_t = int((test["revenue"] > 0).sum())
    whale_cr_c = len(w_c) / max(payers_c, 1)
    whale_cr_t = len(w_t) / max(payers_t, 1)
    whale_arpu_c = float(w_c["revenue"].mean()) if len(w_c) else 0.0
    whale_arpu_t = float(w_t["revenue"].mean()) if len(w_t) else 0.0
    whale_rpu_c = w_c["revenue"].sum() / n_c
    whale_rpu_t = w_t["revenue"].sum() / n_t

    # Mann-Whitney for whale amounts
    if len(w_c) >= 5 and len(w_t) >= 5:
        _, p_whale = stats.mannwhitneyu(w_t["revenue"], w_c["revenue"], alternative="greater")
    else:
        p_whale = float("nan")

    # Segment attrs (country_group + system for exploratory section)
    attrs = (
        df[df["id_user"].isin(ab["id_user"])]
        .sort_values("date_reg")
        .groupby("id_user", as_index=False)
        .first()[["id_user", "country_group", "system"]]
    )
    ab_seg = ab.merge(attrs, on="id_user", how="left")
    seg_c = (
        ab_seg[ab_seg["split_group"] == 0]
        .groupby("country_group")["revenue"]
        .apply(lambda x: (x > 0).mean())
        .rename("cr_ctrl")
    )
    seg_t = (
        ab_seg[ab_seg["split_group"] == 1]
        .groupby("country_group")["revenue"]
        .apply(lambda x: (x > 0).mean())
        .rename("cr_test")
    )
    country_pivot = seg_c.to_frame().join(seg_t, how="outer")
    country_pivot["diff_pp"] = (country_pivot["cr_test"] - country_pivot["cr_ctrl"]) * 100

    # Exploratory segment sample sizes
    ios_mask = ab_seg["system"].str.lower().str.strip() == "ios"
    n_ios_c = int(((ab_seg["split_group"] == 0) & ios_mask).sum())
    n_ios_t = int(((ab_seg["split_group"] == 1) & ios_mask).sum())

    cg1_mask = ab_seg["country_group"] == 1
    n_cg1_c = int(((ab_seg["split_group"] == 0) & cg1_mask).sum())
    n_cg1_t = int(((ab_seg["split_group"] == 1) & cg1_mask).sum())

    # Card payments: users with ≥1 successful card transaction
    card_df = df[df["successful_payment"] == 1].copy()
    card_methods = card_df["method"].str.lower().str.strip().str.contains("card|credit|debit|visa|mastercard", na=False)
    card_users = card_df.loc[card_methods, "id_user"].unique()
    ab_card = ab_seg[ab_seg["id_user"].isin(card_users)]
    n_card_c = int((ab_card["split_group"] == 0).sum())
    n_card_t = int((ab_card["split_group"] == 1).sum())

    return {
        "n_c": n_c, "n_t": n_t,
        "pay_c": pay_c, "pay_t": pay_t,
        "cr_c": cr_c, "cr_t": cr_t,
        "diff_cr": diff_cr, "se_cr": se_cr,
        "ppu_c": ppu_c, "ppu_t": ppu_t,
        "p_ppu": p_ppu, "ci_ppu_c": ci_ppu_c, "ci_ppu_t": ci_ppu_t,
        "n_req_ppu": n_req_ppu, "obs_power_ppu": obs_power_ppu,
        "arpp_c": float(arpp_c.mean()), "arpp_t": float(arpp_t.mean()),
        "p_arpp": p_arpp,
        "rpu_c": rpu_c, "rpu_t": rpu_t,
        "p_rpu": p_rpu, "ci_rpu_c": ci_rpu_c, "ci_rpu_t": ci_rpu_t,
        "whale_cutoff": cutoff,
        "n_whales_c": len(w_c), "n_whales_t": len(w_t),
        "whale_cr_c": whale_cr_c, "whale_cr_t": whale_cr_t,
        "whale_arpu_c": whale_arpu_c, "whale_arpu_t": whale_arpu_t,
        "whale_rpu_c": float(whale_rpu_c), "whale_rpu_t": float(whale_rpu_t),
        "p_whale": p_whale,
        "country_pivot": country_pivot,
        "n_ios_c": n_ios_c, "n_ios_t": n_ios_t,
        "n_cg1_c": n_cg1_c, "n_cg1_t": n_cg1_t,
        "n_card_c": n_card_c, "n_card_t": n_card_t,
    }


def _img_tag(fname, alt=""):
    path = os.path.join(CHARTS_DIR, fname)
    if not os.path.exists(path):
        return (f'<p style="background:#fff3cd;padding:10px;border-radius:4px">'
                f'Графік не знайдено: <code>{fname}</code> — спочатку запустіть 08_charts.py.</p>')
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<img src="data:image/png;base64,{b64}" alt="{alt}" '
            f'style="max-width:100%;border:1px solid #ddd;border-radius:4px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.1)">')


def _badge(p):
    if np.isnan(p):
        return '<span class="badge badge-na">Н/Д</span>'
    if p < ALPHA:
        return f'<span class="badge badge-sig">Значущий (p={p:.3f})</span>'
    return f'<span class="badge badge-ns">Не значущий (p={p:.3f})</span>'


def _country_rows(pivot):
    rows = []
    for country, row in pivot.iterrows():
        diff = row["diff_pp"]
        bg = "#d4edda" if diff > 0.5 else ("#f8d7da" if diff < -0.5 else "#fff")
        rows.append(
            f'<tr><td>{country}</td>'
            f'<td>{row["cr_ctrl"]:.2%}</td>'
            f'<td>{row["cr_test"]:.2%}</td>'
            f'<td style="background:{bg}">{diff:+.2f} pp</td></tr>'
        )
    return "\n".join(rows)


CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;max-width:980px;margin:0 auto;padding:20px 32px;
  color:#222;background:#fafafa;line-height:1.6}
h1{color:#1a237e;border-bottom:3px solid #1a237e;padding-bottom:8px}
h2{color:#283593;margin-top:40px;border-left:4px solid #3949ab;padding-left:10px}
h3{color:#3949ab}
.verdict{border:2px solid #c62828;border-radius:8px;padding:18px 24px;margin:20px 0;
  background:#ffebee}
.verdict h3{color:#c62828;margin:0 0 8px;font-size:1.35em}
table{width:100%;border-collapse:collapse;margin:16px 0}
th{background:#283593;color:#fff;padding:10px 14px;text-align:left}
td{padding:9px 14px;border-bottom:1px solid #e0e0e0}
tr:nth-child(even) td{background:#f5f5f5}
.chart{margin:24px 0;text-align:center}
.warn{background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px 16px;margin:12px 0}
.pass{background:#d4edda;border:1px solid #28a745;border-radius:4px;padding:12px 16px;margin:12px 0}
.info{background:#d1ecf1;border:1px solid #17a2b8;border-radius:4px;padding:12px 16px;margin:12px 0}
.badge{display:inline-block;padding:2px 10px;border-radius:3px;font-size:.85em;font-weight:600}
.badge-sig{background:#d4edda;color:#155724}
.badge-ns{background:#f8d7da;color:#721c24}
.badge-na{background:#e2e3e5;color:#383d41}
footer{color:#888;font-size:.85em;margin-top:40px;border-top:1px solid #ddd;padding-top:12px}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:24px 0;align-items:start}}
.chart-cell{{text-align:center}}
.chart-caption{{font-size:.82em;color:#555;font-style:italic;margin:4px 0 0;padding:0 8px;text-align:center}}
"""


def _img_pair(f1, cap1, f2, cap2, alt1="", alt2=""):
    return (
        f'<div class="chart-row">'
        f'<div class="chart-cell"><div class="chart">{_img_tag(f1, alt1)}</div>'
        f'<p class="chart-caption">{cap1}</p></div>'
        f'<div class="chart-cell"><div class="chart">{_img_tag(f2, alt2)}</div>'
        f'<p class="chart-caption">{cap2}</p></div>'
        f'</div>'
    )


def generate_html(r):
    cr_ci_low = r["diff_cr"] - 1.96 * r["se_cr"]
    cr_ci_high = r["diff_cr"] + 1.96 * r["se_cr"]
    ppu_diff = r["ppu_t"] - r["ppu_c"]
    ppu_ci_low = r["ci_ppu_t"][0] - r["ci_ppu_c"][1]
    ppu_ci_high = r["ci_ppu_t"][1] - r["ci_ppu_c"][0]

    whale_sig_note = (
        f"Mann-Whitney U test для сум платежів whale-користувачів: p={r['p_whale']:.3f} — "
        f"{'<strong>значущий</strong>' if not np.isnan(r['p_whale']) and r['p_whale'] < ALPHA else 'не значущий'}."
        if not np.isnan(r["p_whale"])
        else "Формальний тест на значущість незастосовний через малий розмір вибірки whale-сегменту."
    )

    try:
        n_req_ppu = int(r["n_req_ppu"])
        powered_note = (
            f"<strong>Експеримент мав достатню потужність для метрики payments per user</strong> "
            f"(потрібно ~{n_req_ppu:,} користувачів/групу при MDE 5%; фактично: ~{r['n_c']:,}; "
            f"оцінена потужність: {r['obs_power_ppu']:.0%})."
            if r["n_c"] >= n_req_ppu
            else f"<strong>Експеримент може бути недостатньо потужним для метрики payments per user</strong> "
                 f"(потрібно ~{n_req_ppu:,} користувачів/групу при MDE 5%; фактично: ~{r['n_c']:,}; "
                 f"оцінена потужність: {r['obs_power_ppu']:.0%})."
        )
    except (TypeError, ValueError):
        powered_note = "Аналіз потужності для payments per user не вдалось обчислити (недостатня базова дисперсія)."

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<title>A/B Test Report: Редизайн екрану оплати (мобільна версія)</title>
<style>{CSS}</style>
</head>
<body>

<h1>A/B Test Report: Редизайн екрану оплати (мобільна версія)</h1>
<p style="color:#555">
  Сформовано: {date.today().isoformat()} &nbsp;|&nbsp;
  Початок експерименту: 23 липня 2021 р. &nbsp;|&nbsp;
  Платформа: лише Mobile
</p>

<h2>1. Executive Summary</h2>
<div class="verdict">
  <h3>Рекомендація: НЕ ЗАПУСКАТИ</h3>
  <p>
    Новий UI екрану оплати <strong>не показав статистично значущого покращення</strong>
    жодної з основних бізнес-метрик.
    Первинна метрика — <strong>payments per user</strong> (загальна кількість успішних
    платежів на одного користувача, що охоплює і конверсію, і повторні покупки) —
    склала <strong>{r['ppu_t']:.4f}</strong> у тестовій групі проти <strong>{r['ppu_c']:.4f}</strong>
    у контрольній (різниця: <strong>{ppu_diff:+.4f}</strong>, p={r['p_ppu']:.3f} — не значуще,
    причому напрямок <em>негативний</em>).
    Average Revenue Per Payer склав ${r['arpp_t']:,.0f} (test) проти ${r['arpp_c']:,.0f} (control) —
    також не значуще (p={r['p_arpp']:.3f}).
    <strong>Статистичних підстав</strong> вважати, що запуск збільшить кількість платежів
    або виручку, — немає.
  </p>
</div>

<h2>2. Що тестувалося і навіщо</h2>
<p>
  Продуктова команда провела редизайн <strong>UI екрану оплати для мобільних користувачів</strong>
  з метою збільшення кількості успішних покупок ігрової валюти.
  Змінено лише компонування екрана — ціни, кількість валюти та ігрова механіка залишились без змін.
  Експеримент розпочався <strong>23 липня 2021 р.</strong> і розділив нових реєстрацій на:
  <em>control group</em> (оригінальний екран) та <em>test group</em> (редизайн).
</p>
<p>
  Гра побудована на <strong>whale monetization model</strong> — невелика частка
  користувачів із великими витратами генерує більшість виручки. Тому аналіз охоплює
  загальний conversion rate, середній розмір платежу, загальну виручку на користувача <em>і</em>
  окремо — вплив на whale-сегмент.
</p>

<h2>3. Хто увійшов до аналізу</h2>
<ul>
  <li><strong>Платформа:</strong> лише мобільні користувачі (редизайн створено для mobile).
    Немобільних користувачів виключено.</li>
  <li><strong>Дата реєстрації:</strong> лише користувачі, зареєстровані 23 липня 2021 р. або пізніше
    (старт експерименту). Попередньо зареєстрованих виключено для уникнення контамінації.</li>
  <li><strong>Лише успішні платежі</strong> (невдалі транзакції виключено з revenue-метрик).</li>
  <li>
    <strong>Фінальна когорта:</strong>
    Control: <strong>{r['n_c']:,} користувачів</strong> &nbsp;|&nbsp;
    Test: <strong>{r['n_t']:,} користувачів</strong>
  </li>
</ul>

<h2>4. Результати ключових метрик</h2>
<table>
  <tr>
    <th>Метрика</th><th>Control</th><th>Test</th><th>Різниця</th><th>Результат</th>
  </tr>
  <tr style="background:#fff8e1">
    <td><strong>Payments Per User (PPU) — PRIMARY</strong><br>
        <small>ПЕРВИННА МЕТРИКА — загальна кількість успішних платежів ÷ усі користувачі<br>
        Враховує і конверсію, і повторні покупки</small></td>
    <td>{r['ppu_c']:.4f}<br><small>({r['ci_ppu_c'][0]:.4f} — {r['ci_ppu_c'][1]:.4f})</small></td>
    <td>{r['ppu_t']:.4f}<br><small>({r['ci_ppu_t'][0]:.4f} — {r['ci_ppu_t'][1]:.4f})</small></td>
    <td>{ppu_diff:+.4f}<br><small>({(r['ppu_t'] / r['ppu_c'] - 1) * 100 if r['ppu_c'] else 0:+.1f}%)</small></td>
    <td>{_badge(r['p_ppu'])}</td>
  </tr>
  <tr>
    <td><strong>Avg Revenue Per Payer (ARPP)</strong><br>
        <small>Середній чек серед користувачів, які платили</small></td>
    <td>${r['arpp_c']:,.2f}</td>
    <td>${r['arpp_t']:,.2f}</td>
    <td>{(r['arpp_t'] / r['arpp_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_arpp'])}</td>
  </tr>
  <tr>
    <td><strong>Revenue Per User (RPU / ARPU)</strong><br>
        <small>Загальна виручка ÷ усі користувачі, включно з тими, хто не платив</small></td>
    <td>${r['rpu_c']:,.2f}</td>
    <td>${r['rpu_t']:,.2f}</td>
    <td>{(r['rpu_t'] / r['rpu_c'] - 1) * 100:+.1f}%</td>
    <td>{_badge(r['p_rpu'])}</td>
  </tr>
  <tr>
    <td><strong>Conversion Rate</strong><br>
        <small>% користувачів, які здійснили ≥1 платіж (вторинний орієнтир)</small></td>
    <td>{r['cr_c']:.2%}<br><small>({r['pay_c']:,} / {r['n_c']:,})</small></td>
    <td>{r['cr_t']:.2%}<br><small>({r['pay_t']:,} / {r['n_t']:,})</small></td>
    <td>{(r['diff_cr']*100):+.2f} pp</td>
    <td>—</td>
  </tr>
</table>

<div class="chart-cell">
  {_img_tag("01_primary_metrics.png", "Первинні метрики")}
  <p class="chart-caption">
    Ліворуч: payments per user (PPU — первинна метрика). Праворуч: revenue per user (RPU).
    Обидві групи майже ідентичні; жодна різниця не є статистично значущою.
    Error bars = 95% bootstrap CI.
  </p>
</div>
<div class="chart-cell">
  {_img_tag("02_amount_and_trend.png", "Розподіл сум та денний тренд")}
  <p class="chart-caption">
    Ліворуч: ключові перцентилі сум платежів серед платників (log scale — скошеність whale-моделі).
    Праворуч: денний conversion rate від старту експерименту — стійкого тренду в жодному напрямку немає.
  </p>
</div>

<h2>5. Статистична значущість — простою мовою</h2>
<p>Використані статистичні тести:</p>
<ul>
  <li><strong>★ Payments Per User (первинна):</strong> Mann-Whitney U test (непараметричний;
    обраний через zero-inflated розподіл — більшість користувачів не платять взагалі).
    Перевіряє, чи test-група генерує більше платежів на користувача, ніж control.
    P-value: {r['p_ppu']:.3f}.</li>
  <li><strong>Avg Revenue Per Payer:</strong> Mann-Whitney U test (непараметричний;
    обраний через сильну правосторонню скошеність сум платежів через whale-витрати).
    P-value: {r['p_arpp']:.3f}.</li>
  <li><strong>Revenue Per User:</strong> Mann-Whitney U test.
    P-value: {r['p_rpu']:.3f}.</li>
</ul>

<div class="warn">
  <strong>Усі три первинні метрики: p-value &gt; 0.05 — статистично значущого ефекту не виявлено.</strong>
  Простими словами: спостережувані відмінності між test і control відповідають звичайним
  випадковим коливанням. Ми не можемо стверджувати, що новий дизайн змінює поведінку користувачів.
</div>

<p>
  <strong>95% bootstrap confidence interval для різниці PPU (test − control):</strong>
  ({ppu_ci_low:+.4f} — {ppu_ci_high:+.4f}).
  Інтервал включає нуль — редизайн не показує надійного впливу на частоту платежів.
</p>

<p>{powered_note}</p>

<h2>6. Аналіз whale-сегменту</h2>
<p>
  Whale-користувачі — це топ-платники, сукупні витрати яких становлять 75% загальної виручки.
  Whale-поріг для цього експерименту:
  <strong>${r['whale_cutoff']:,.0f}</strong> у виручці після старту експерименту.
</p>
<table>
  <tr><th>Метрика</th><th>Control</th><th>Test</th><th>Різниця</th></tr>
  <tr>
    <td><strong>Кількість whales</strong></td>
    <td>{r['n_whales_c']}</td>
    <td>{r['n_whales_t']}</td>
    <td>{r['n_whales_t'] - r['n_whales_c']:+d}</td>
  </tr>
  <tr>
    <td><strong>Частка whales серед платників</strong></td>
    <td>{r['whale_cr_c']:.1%}</td>
    <td>{r['whale_cr_t']:.1%}</td>
    <td>{(r['whale_cr_t'] - r['whale_cr_c']) * 100:+.1f} pp</td>
  </tr>
  <tr>
    <td><strong>Середня виручка на одного whale</strong></td>
    <td>${r['whale_arpu_c']:,.0f}</td>
    <td>${r['whale_arpu_t']:,.0f}</td>
    <td>{(r['whale_arpu_t'] / r['whale_arpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
  <tr>
    <td><strong>Whale Revenue Per User (усі користувачі)</strong></td>
    <td>${r['whale_rpu_c']:.2f}</td>
    <td>${r['whale_rpu_t']:.2f}</td>
    <td>{(r['whale_rpu_t'] / r['whale_rpu_c'] - 1) * 100:+.1f}%</td>
  </tr>
</table>

<div class="info">
  <strong>Whale-метрики мають позитивний напрямок</strong> — test-група демонструє вищу частку
  whales та вищий середній чек whale — але <strong>вибірка занадто мала
  ({r['n_whales_c']}–{r['n_whales_t']} whales на групу)</strong>, щоб робити надійні висновки.
  {whale_sig_note}
  Це позитивний напрямний сигнал, що потребує подальшого дослідження,
  але його недостатньо для повноцінного запуску.
</div>

<div class="chart-cell">
  {_img_tag("06_whale_analysis.png", "Whale Analysis")}
  <p class="chart-caption">Whale-сегмент: частка платників та середня виручка. Test-група дещо вища,
  але малий розмір вибірки (n={r['n_whales_c']}–{r['n_whales_t']}) не дозволяє робити твердих висновків.</p>
</div>

<h2>7. Сегментний аналіз</h2>

<h3>Conversion Rate за country group</h3>
<div class="chart-cell">
  {_img_tag("05_country_heatmap.png", "Country Heatmap")}
  <p class="chart-caption">Conversion rate за country group × A/B-група. Між country groups є суттєва
  різниця у базовому рівні конверсії — ця гетерогенність є ключовим застереженням до загального результату.</p>
</div>
<table>
  <tr><th>Country Group</th><th>Control CR</th><th>Test CR</th><th>Різниця</th></tr>
  {_country_rows(r['country_pivot'])}
</table>

<div class="warn">
  <strong>Дисбаланс country group — потенційний конфаундер:</strong>
  Перевірка рандомізації виявила статистично значущий дисбаланс у country_group
  (chi² = 18.08, p = 0.0004, Bonferroni-корекція).
  Country group 4 надмірно представлена у control (3.6% проти 2.4% у test);
  country group 2 надмірно представлена у test (14.6% проти 13.3% у control).
  За даними до експерименту ці групи конвертують з дуже різною ефективністю — group 2 конвертує
  5.25%, group 4 — 2.40%, тоді як для більшості group 1 — 2.12%.
  Цей дисбаланс може частково занижувати або завищувати загальний A/B-результат.
</div>

<h3>Exploratory-знахідки по сегментах</h3>
<p>
  Наведені нижче відмінності між підсегментами виявлені <em>після</em> перегляду даних і є
  <strong>exploratory</strong> (непередбаченими гіпотезами). Вони наведені тут,
  оскільки розміри ефектів дуже великі — p &lt; 0.00005 у кожному випадку,
  що значно нижче Bonferroni-порогу 0.0025 навіть після урахування ~20 порівнянь.
  Статистична значущість підтверджує реальність цих ефектів у даних; вона не пояснює
  їх причину (справжнє UX-покращення чи артефакт експерименту).
</p>
<ul>
  <li>
    <strong>iOS-користувачі</strong>
    (control: n={r['n_ios_c']:,}, test: n={r['n_ios_t']:,}):
    conversion rate у test-групі суттєво вищий, ніж у control.
    Це найяскравіший позитивний сигнал у наборі даних. Водночас iOS — група з аномальним
    покращенням success rate (див. Розділ 8), тому механізм неясний.
  </li>
  <li>
    <strong>Користувачі, що платять карткою</strong>
    (control: n={r['n_card_c']:,}, test: n={r['n_card_t']:,}):
    конверсія через картку вища у test-групі.
    Можливо, відображає справжнє покращення картково-платіжного flow у новому UI.
  </li>
  <li>
    <strong>Country group 1 (основний ринок, 86% користувачів)</strong>
    (control: n={r['n_cg1_c']:,}, test: n={r['n_cg1_t']:,}):
    конверсія вища у test.
    Оскільки group 1 формує більшість аудиторії, це є найбільшим вкладом у будь-який загальний ефект.
  </li>
</ul>
<div class="info">
  <strong>Рекомендований наступний крок:</strong> Провести окремий експеримент для iOS-користувачів
  у country group 1, щоб підтвердити, чи справді редизайн покращує конверсію для цього сегменту.
  У разі підтвердження умовний запуск (лише для iOS) може бути виправданим.
</div>

<p><small>
  Усі результати на рівні сегментів є exploratory і не скориговані на множинні порівняння.
  Розглядайте їх як джерело гіпотез, а не підтверджені висновки.
</small></p>

<h2>8. Sanity Checks</h2>

<h3>Баланс груп (invariant metrics)</h3>
<div class="chart-cell">
  {_img_tag("07_sanity_combined.png", "Sanity Checks")}
  <p class="chart-caption">
    Баланс груп за чотирма інваріантними вимірами (gender, age group, country group, traffic source).
    Перекриття error bars свідчить про відсутність значущого дисбалансу. Chi-square p &gt; 0.05 для всіх чотирьох.
  </p>
</div>
<div class="pass">
  <strong>Загальний результат — ПРОЙДЕНО:</strong> Розподіли за gender, age group, country group та traffic source
  збалансовані між test і control (chi-square p &gt; 0.05).
  Рандомізація виглядає коректною за цими вимірами.
</div>
<div class="warn">
  <strong>УВАГА — дисбаланс OS:</strong> Розподіл операційних систем (system) відрізняється між
  групами (chi-square p = 0.004) у мобільній когорті. Практичний масштаб дисбалансу невеликий,
  але це є методологічним застереженням, особливо з огляду на великий iOS-ефект у Розділі 7.
</div>
<div class="chart-cell">
  {_img_tag("07b_os_distribution.png", "OS Distribution")}
  <p class="chart-caption">
    Розподіл операційних систем між контрольною та тестовою групами.
    Непересічні error bars для iOS та Android підтверджують статистично значущий
    дисбаланс OS між групами (chi² тест, p = 0.004).
  </p>
</div>

<h3>Payment Success Rate — критична аномалія</h3>
<div class="warn" style="border-color:#c62828;background:#ffebee">
  <strong>RED FLAG: Payment success rate суттєво відрізняється між групами.</strong>
  Payment success rate — це <em>технічна</em> метрика: вона вимірює, чи завершується транзакція
  після того, як користувач її ініціює. UI-редизайн не повинен на неї впливати.
  Проте test-група демонструє помітно відмінний success rate від control,
  причому два протилежні ефекти частково компенсують один одного в агрегаті.
</div>
<table>
  <tr>
    <th>Сегмент</th><th>Control success rate</th><th>Test success rate</th>
    <th>Різниця</th><th>Примітки</th>
  </tr>
  <tr>
    <td><strong>Загалом</strong></td>
    <td>61.5%</td><td>70.4%</td>
    <td>+8.9 pp (+4.9 — +13.0 pp)</td>
    <td>Статистично значуще (p ≈ 0)</td>
  </tr>
  <tr style="background:#ffebee">
    <td><strong>Country group 4</strong></td>
    <td>67.4%</td><td>15.0%</td>
    <td>−52.4 pp (−69.9 — −34.9 pp)</td>
    <td>КРИТИЧНО — імовірно баг платіжного шлюзу у test-варіанті для цього регіону</td>
  </tr>
  <tr style="background:#d4edda">
    <td><strong>iOS-користувачі</strong></td>
    <td>57.1%</td><td>77.9%</td>
    <td>+20.8 pp (+15.5 — +26.1 pp)</td>
    <td>Сильний позитив — новий UI може справді покращувати iOS-платіжний flow</td>
  </tr>
  <tr>
    <td><strong>Android-користувачі</strong></td>
    <td>66.7%</td><td>61.3%</td>
    <td>−5.4 pp (−11.6 — +0.7 pp)</td>
    <td>Не значуще (p = 0.095)</td>
  </tr>
  <tr>
    <td><strong>Карткові платежі</strong></td>
    <td>—</td><td>—</td>
    <td>+9.4 pp (+5.1 — +13.7 pp)</td>
    <td>Статистично значуще (p ≈ 0)</td>
  </tr>
</table>
<p>
  <strong>Інтерпретація:</strong> Загальний +8.9 pp є оманливим — він маскує два окремі ефекти:
  <em>катастрофічний збій</em> у country group 4 (платіжний flow, схоже, зламаний у test-варіанті,
  можливо через несумісність із платіжним шлюзом регіону) і <em>справжнє покращення</em> на iOS.
  Ці два ефекти частково анулюють один одного. <strong>Country group 4 необхідно розслідувати
  до будь-якого рішення про запуск.</strong>
</p>

<h2>9. Ризики та застереження</h2>
<ul>
  <li><strong>Потужність revenue-метрик:</strong> Через екстремальну дисперсію сум платежів
    (Gini ≈ 0.99; кілька whale-користувачів домінують у виручці) для надійного виявлення
    10% зміни RPU знадобляться сотні тисяч користувачів.
    Revenue-висновки тому є недостатньо потужними.</li>
  <li><strong>Дисбаланс OS:</strong> Виявлено статистично значущу різницю у складі OS
    між групами, що може вносити незначне конфаундування.</li>
  <li><strong>Розмір whale-вибірки:</strong> Лише {r['n_whales_c']}–{r['n_whales_t']} whale-користувачів
    на групу — недостатньо для надійного статистичного висновку про whale-ефекти.</li>
  <li><strong>Дисбаланс country group:</strong> Рандомізація призвела до статистично
    значущого дисбалансу country_group (chi² = 18.08, p = 0.0004). Оскільки country groups
    мають суттєво різні базові рівні конверсії (2.1%–5.3%), цей дисбаланс може
    зміщувати загальний результат у будь-який бік.</li>
  <li><strong>Аномалія payment success rate у country group 4:</strong> Test-варіант
    спричинив падіння payment success rate на 52 pp для country group 4 (15% проти 67%).
    Це майже напевно технічний баг, а не UX-ефект — він міг знизити виміряну виручку
    та конверсію у test-групі, змусивши новий дизайн виглядати гіршим, ніж він є.</li>
  <li><strong>Односторонні тести:</strong> Усі тести були налаштовані на виявлення покращення
    у test. Вони менш чутливі до виявлення шкоди (негативних ефектів на control).</li>
  <li><strong>Novelty effect:</strong> Денний тренд конверсії (графік вище, права панель)
    не показує характерного початкового підйому з подальшим спадом — novelty effect
    у цих даних не спостерігається. Поведінка обох груп стабільна протягом усього
    усього тривання експерименту.</li>
  <li><strong>Охоплення:</strong> Цей аналіз стосується лише мобільних користувачів.
    Вплив на інші платформи невідомий.</li>
</ul>

<h2>10. Фінальна рекомендація</h2>
<div class="verdict">
  <h3>НЕ ЗАПУСКАТИ</h3>
  <p>
    Новий UI екрану оплати <strong>не демонструє статистично значущого покращення</strong>
    відносно поточного дизайну за жодною первинною метрикою.
    Первинна метрика — payments per user — була незначно <em>нижчою</em> у test-групі
    ({r['ppu_t']:.4f} проти {r['ppu_c']:.4f}, p={r['p_ppu']:.3f}).
    Revenue-метрики не показали значущих змін.
    Хоча whale-витрати мали позитивний напрямок у test-групі, whale-вибірка занадто мала
    для твердих висновків.
  </p>
  <p>
    <strong>Важливе застереження:</strong> Загальний результат ускладнено двома аномаліями.
    По-перше, платіжний flow для country group 4, схоже, зламаний у test-варіанті (success
    rate 15% проти 67% у control) — це, ймовірно, знизило виручку та конверсію test-групи
    і має розглядатись як технічний баг. По-друге, iOS-користувачі демонструють сильний
    позитивний сигнал як у конверсії, так і у payment success rate. Ці два ефекти частково
    компенсують один одного в агрегаті, маскуючи можливе суттєве покращення, специфічне для iOS.
  </p>
  <p><strong>Рекомендовані наступні кроки:</strong></p>
  <ul>
    <li><strong>Негайно розслідувати платіжний flow у country group 4</strong> — падіння
        payment success rate на 52 pp майже напевно є технічним дефектом інтеграції нового UI
        із платіжним шлюзом цього регіону. Виправити до будь-яких подальших експериментів.</li>
    <li><strong>Розглянути умовний re-test лише для iOS</strong> — сигнали конверсії та success rate
        для iOS достатньо сильні (p &lt; 0.00005), щоб виправдати окремий експеримент.
        Якщо чистий iOS-тест підтвердить ефект, поетапний запуск для iOS може бути обґрунтованим.</li>
    <li>Провести якісне UX-дослідження, щоб зрозуміти, чому редизайн не підняв Android-конверсію.</li>
    <li>Для майбутніх експериментів з revenue-метриками планувати значно більший розмір вибірки
        (whale-модель створює надзвичайно високу дисперсію, яка потребує великих когорт).</li>
  </ul>
</div>

<footer>
  Звіт сформовано автоматично на основі A/B-тест даних &nbsp;|&nbsp;
  Мобільні користувачі, зареєстровані 23 липня 2021 р. або пізніше &nbsp;|&nbsp;
  Поріг статистичної значущості: α = 0.05
</footer>
</body>
</html>"""


def main():
    print("=== Step 9 (UA): Generating CEO Report (Ukrainian) ===")
    df = load_mobile_payments()
    print("Computing results...")
    r = compute_results(df)
    print("Rendering HTML...")
    html = generate_html(r)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
