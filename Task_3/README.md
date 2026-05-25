# HabitONE Competitive Analysis

Pricing and catalog intelligence for 17 US functional-coffee brands. Data collected from own-site storefronts and eBay listings; stored in SQLite; analyzed with 8 SQL queries.

---

## Competitors

| # | Brand | Website | Why included |
|---|---|---|---|
| 1 | **HabitONE** *(subject)* | habitone.co | Subject brand; marked `is_habitone=1` |
| 2 | Four Sigmatic | foursigmatic.com | Market pioneer; widest format range (instant, packet, ground, pods) |
| 3 | Ryze | ryzesuperfoods.com | DTC-only; 16k+ reviews; 6-mushroom blend |
| 4 | MudWtr | mudwtr.com | Coffee alternative; strong subscription model |
| 5 | Everyday Dose | everydaydose.com | Lion's Mane + collagen + L-theanine stack |
| 6 | Shroomi | drinkshroomi.com | Bon Appétit "Best of 2025"; organic |
| 7 | Rasa | rasacoffee.com | Adaptogen-heavy; subscription-first |
| 8 | Om Mushrooms | ommushrooms.com | Capsule + powder; supplement-oriented |
| 9 | BodyBrain Coffee | bodybraincoffee.com | Tongkat Ali + Lion's Mane differentiation |
| 10 | IQJOE (IQBAR) | eatiqbar.com | Lion's Mane + Magnesium L-Threonate; nootropic focus |
| 11 | Clevr Blends | clevrblends.com | Premium adaptogenic lattes; creamer format |
| 12 | Strong Coffee Co. | strongcoffeecompany.com | Adaptogen instant; broad retail presence |
| 13 | La Republica | larepublicacoffee.com | Organic mushroom coffee; Amazon-native |
| 14 | Renude | drinkrenude.com | Chagaccino powder; woman-owned |
| 15 | North Spore | northspore.com | Ground coffee; 12,000mg fruiting body extracts |
| 16 | Nootrum | nootrum.com | FDA-registered facility; Amazon bestseller list |
| 17 | Pella Nutrition | mypellanutrition.com | 7-mushroom blend; 60-serving SKUs |

---

## Data Collection

**Date collected:** 2026-05-20  
**Method:** Scripted scraping

- **Own sites:** `requests` + `BeautifulSoup` (static HTML); auto-fallback to `Playwright` (JS-rendered storefronts). Rate-limited to a randomized 2–5 s delay between requests.
- **eBay:** eBay Browse API (`/buy/browse/v1/item_summary/search`). Credentials loaded from `.env`.
- **Amazon:** Manual collection only — place a filled `data/raw/amazon_manual.csv` (same column schema as other CSVs) before running `02_load_db.py`.

### Known limitations

- CSS selectors are based on common Shopify patterns and may need adjustment for non-Shopify storefronts. Check `data/raw/scrape_errors.log` after a run.
- eBay sandbox credentials (`SBX` in APP_ID) return synthetic data. Swap in production keys to get real listings.
- Serving-size and serving-count values are inferred from product descriptions via regex; NULL where not parseable — do not impute.
- Amazon prices are not included until manual CSV is provided.

---

## How to run

```bash
pip install -r requirements.txt
playwright install chromium

python scripts/01_scrape.py    # writes data/raw/<brand>.csv (one per brand)
python scripts/02_load_db.py   # builds db/competitors.db
sqlite3 db/competitors.db < scripts/03_queries.sql
```

---

## Key findings

*(Populated after data collection. See `outputs/analysis_summary.md` for full analysis.)*


● Стан на зараз

  Що недоробив — 02_load_db.py

  Правка наполовину вставлена (є product_serving_count в логіці, але не оголошений словник і 
  не заповнюється при INSERT INTO products). Потрібно:

  1. Додати до блоку if product_id not in seen_products: рядок:
  sc_val = _int(row.get("serving_count", ""))
  if sc_val and sc_val > 0:
      product_serving_count[product_id] = sc_val
  2. Запустити python scripts/02_load_db.py → перевірити що missing_sp зменшилось (очікую ~7 
  менше — Rasa ×2, Four Sigmatic ×4, BodyBrain ×1).

  Що не виправиться ніколи: Laird (126) і Ryze (22) — у скрейпері не зібрано serving_count.  
  Це структурна дірка даних, не баг скрипту.

  ---
  Що писати в українському аналізі

  Всі числа оновлені — просто переписати українську версію по структурі англійської
  (analysis_summary.md). Ключові зміни відносно старої analysis_summary_ua.md:

  ┌───────────────────────┬─────────────────┬────────────────────────────────────────────┐   
  │       Показник        │    Було (UA)    │                   Стало                    │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Price rows            │ 985             │ 960                                        │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Four Sigmatic         │ 60              │ 45                                         │   
  │ products              │                 │                                            │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Laird products        │ 40              │ 34                                         │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Ryze products         │ 45              │ 25                                         │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Відсутні формати (Q6) │ 6 (incl. rtd,   │ 4 (capsule, ground, packet, pods)          │   
  │                       │ whole)          │                                            │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Own-site avg HabitONE │ $87.23          │ $71.16                                     │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Новий Висновок 8      │ немає           │ Amazon vs own-site динаміка (Clevr/MudWtr  │   
  │                       │                 │ модель)                                    │   
  ├───────────────────────┼─────────────────┼────────────────────────────────────────────┤   
  │ Примітка по           │ 41% без vol_g   │ 18% без serving_price; Laird і Ryze        │   
  │ serving_price         │                 │ структурно не покриті                      │   
  └───────────────────────┴─────────────────┴────────────────────────────────────────────┘   

  Решта чисел (68-й перцентиль, $0.185/г, $1.28/порцію, 37% sub discount, HabitONE 5
  продуктів) — не змінились.
