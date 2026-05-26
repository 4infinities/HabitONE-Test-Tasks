# HabitONE — Конкурентний аналіз цін та каталогу

Цінова та каталогова розвідка по 23 американських брендах функціональної кави. Дані зібрані скрейперами з власних сайтів та Amazon, збережені в SQLite, проаналізовані 10 SQL-запитами.

Повний аналіз: [`analysis_summary_ua.md`](analysis_summary_ua.md)

---

## Конкуренти

| # | Бренд | Сайт | Чому включений |
|---|---|---|---|
| 1 | **HabitONE** *(суб'єкт)* | habitone.co | Досліджуваний бренд; `is_habitone=1` |
| 2 | Four Sigmatic | foursigmatic.com | Піонер ринку; найширший діапазон форматів |
| 3 | Ryze | ryzesuperfoods.com | DTC-only; 16k+ відгуків; 6-гриб бленд |
| 4 | MudWtr | mudwtr.com | Замінник кави; сильна модель підписки |
| 5 | Everyday Dose | everydaydose.com | Lion's Mane + колаген + L-теанін |
| 6 | Shroomi | drinkshroomi.com | Bon Appétit "Best of 2025"; органік |
| 7 | Rasa | rasacoffee.com | Адаптоген-акцент; subscription-first |
| 8 | Om Mushrooms | ommushrooms.com | Капсули + порошок; орієнтація на БАД |
| 9 | BodyBrain Coffee | bodybraincoffee.com | Tongkat Ali + Lion's Mane |
| 10 | IQJOE (IQBAR) | eatiqbar.com | Lion's Mane + Magnesium L-Threonate |
| 11 | Clevr Blends | clevrblends.com | Преміум адаптогенні лате; формат кремера |
| 12 | Strong Coffee Co. | strongcoffeecompany.com | Адаптоген instant; широка роздрібна присутність |
| 13 | La Republica | larepublicacoffee.com | Органічна грибна кава; Amazon-native |
| 14 | Renude | drinkrenude.com | Chagaccino powder; woman-owned |
| 15 | North Spore | northspore.com | Ground coffee; 12,000mg екстрактів |
| 16 | Nootrum | nootrum.com | FDA-registered; Amazon bestseller |
| 17 | Pella Nutrition | mypellanutrition.com | 7-гриб бленд; SKU по 60 порцій |
| 18 | Laird Superfood | lairdsuper.com | Функціональні кремери + instant |
| 19 | Max Fit Wellness | maxfitwellness.com | Shopify; функціональні wellness-порошки |
| 20 | Bunkell | amazon.com/stores/Bunkell | Amazon-native; грибна кава |
| 21 | Taoters | amazon.com/stores/Taoters | Amazon-native; грибна кава |
| 22 | VenturePal | amazon.com | Amazon-native; функціональна кава |
| 23 | Lucid | amazon.com | Amazon-native; ноотропна кава |

---

## Методологія збору даних

### Стратегія скрейпінгу

Збір даних ведеться двома окремими шляхами:

**Власні сайти** (`scripts/website_scrapers/`)
- Базовий підхід: `requests` + `BeautifulSoup` для статичного HTML
- Fallback: `Playwright` через `playwright_base.py` для JS-рендерених сторінок (Shopify з динамічними варіантами, React-стори)
- Кожен бренд — окремий скрейпер; шаблон — `scripts/shopify_scraper_template.py`
- Затримка між запитами: 2–5 секунд рандомізовано

**Amazon** (`scripts/amazon scrapers/`)
- Playwright (Chromium) через ScrapeGraphAI `ChromiumLoader` — без LLM, лише як браузерний рушій
- Перед будь-яким `import scrapegraphai` необхідний compatibility shim для langchain_community v0.4:
  ```python
  from langchain_ollama import ChatOllama as _ChatOllama
  import langchain_community.chat_models as _lcm
  if not hasattr(_lcm, 'ChatOllama'):
      _lcm.ChatOllama = _ChatOllama
  ```
- Затримка між сторінками продуктів: `random.uniform(4, 7)` секунд
- `load_state="load"` — `networkidle` таймаутує на Amazon, `domcontentloaded` не вантажить JS-ціни
- Шаблон — `scripts/amazon scrapers/amazon_scraper_template.py`

### Що збирається по кожному SKU

| Поле | Приклад | Примітка |
|---|---|---|
| brand | "Four Sigmatic" | точна назва бренду |
| product_name | "Think Coffee with Lion's Mane" | як на сайті |
| format | "instant" | з таксономії нижче |
| serving_size_g | 6.0 | грам на порцію; NULL якщо не вдалося знайти |
| serving_count | 30 | кількість порцій у пакованні |
| volume_g | 180 | загальна вага пакування = serving_size_g × serving_count |
| price_usd | 39.99 | ціна як відображається на сайті |
| discount_pct | 15 | % знижки; 0 якщо немає |
| serving_price | 1.33 | price_usd / serving_count |
| key_ingredient | "lion's mane" | основна функціональна складова |
| channel | "amazon" | own_site / amazon |
| url | https://... | джерело |
| date_collected | 2026-05-20 | ISO формат |
| purchase_type | "subscription" | subscription / single / NULL |

### Таксономія форматів

| Значення | Опис |
|---|---|
| `instant` | Розсипний порошок у банці/пакеті, дозується ложкою |
| `packet` | Порційні саше на одне приготування |
| `ground` | Мелена кава |
| `capsule` | Капсули або таблетки |
| `rtd` | Ready-to-drink: банки або пляшки |
| `pods` | K-cup або інший формат капсул для кавомашини |
| `creamer` | Функціональний кремер або добавка |
| `bundle` | Набір з кількох SKU |
| `other` | Все інше |

---

## Технічні складнощі та рішення

### Amazon — блокування ботів
Amazon агресивно блокує автоматичні запити. Рішення: Playwright з реалістичними headers і рандомізованими затримками. Більшість скрейперів проходять через `load_state="load"` (не `networkidle`). Якщо CAPTCHA — перезапустити через 10–15 хвилин.

### Назви продуктів Amazon vs сайт
Amazon-назви продуктів значно довші та інші, ніж на власному сайті. Приклад: "Ryze Mushroom Coffee – Organic Arabica, 6 Mushroom Blend, 30 Servings" vs сайтовий "Original Mushroom Coffee". Скрипт `05_assign_ids.py` автоматично зіставляє назви між каналами по нормалізованому fuzzy-ключу. Рядки, які не вдалося зіставити автоматично, потрапляють у `unmatched_review.csv` для ручного перегляду.

### Варіанти розміру як окремі рядки
HabitONE та інші бренди продають один продукт у кількох розмірах (1 банка / 2 банки / 3 банки). Кожен розмір — окремий рядок у даних. `05_assign_ids.py` групує їх під один `product_id` за правилом: однакова назва після видалення токенів розміру (числа + "servings", "pack", "oz" тощо).

### Дублікати між каналами
Один і той самий продукт може з'явитися і на власному сайті, і на Amazon. `05_assign_ids.py` присвоює їм спільний `product_id`, щоб `products` таблиця не дублювала записи. Ціни при цьому — окремі рядки в таблиці `prices` з різним `channel`.

### Відсутній serving_count у Laird та Ryze
Скрейпери цих брендів не зібрали `serving_count` — він не був явно вказаний на сторінках продуктів у момент збору. Через це 148 рядків (Laird 126 + Ryze 22) не мають `serving_price`. Це структурна прогалина даних, яка не виправляється без повторного збору.

### Перезапуск окремих брендів
Після виявлення помилок у зібраних даних кілька брендів потребували часткового перезапуску:
- **Laird Superfood** — `scripts/laird_rerun_*.py`: повторний збір сайту та Amazon, матчинг, інтеграція
- **Ryze** — `scripts/ryze_rerun_match.py`: перематчинг після виправлення назв
- **Four Sigmatic** — `scripts/foursigmatic_rerun_*.py`: перематчинг Amazon-рядків після коригування

Утиліта `scripts/patch_brand.py` дозволяє замінити дані одного бренду в `all_brands.csv` без повного перезапуску пайплайну:
```
python scripts/patch_brand.py --brand "Laird Superfood" --channel amazon --file data/raw/laird_amazon.csv
```

### Нормалізація назв брендів
Скрейпери іноді записували різні варіанти назви одного бренду (наприклад, "Strong Coffee Company" і "Strong Coffee Co."). `07_cleanup_ids.py` містить словник аліасів і нормалізує всі рядки до canonical-назви.

---

## Ручні втручання

Ці дії виконувалися вручну і не відтворюються скриптами:

1. **`data/processed/unmatched_review.csv`** — після запуску `06_fill_unmatched_ids.py` частина рядків не отримала `product_id` автоматично. Кожен такий рядок переглядався вручну: або присвоювався існуючий `product_id`, або новий. Файл редагувався безпосередньо в Excel/CSV-редакторі.

2. **Фільтрація нерелевантних продуктів** — `04_filter_merge.py` відкидає аксесуари, одяг, подарункові картки та некавові добавки (електроліти, матча, какао тощо). Граничні випадки (наприклад, чисті грибні капсули без кави) позначалися вручну в `data/processed/rejected_manual.csv`.

3. **Перевірка одного пілотного рядка перед повним запуском** — для кожного Amazon-скрейпера спочатку запускався pilot на одному ASIN, результат перевірявся вручну проти живої сторінки Amazon (ціна, назва, знижка, кількість порцій), і лише після підтвердження запускався повний збір.

---

## Структура репозиторію та порядок запуску

```
habitone-competitive-analysis/
│
├── data/
│   ├── raw/                        ← вихідні CSV від скрейперів (не змінювати!)
│   └── processed/                  ← нормалізовані CSV після пайплайну
│       ├── all_brands.csv          ← merged + filtered
│       ├── all_brands_ids.csv      ← з brand_id і product_id
│       ├── unmatched_review.csv    ← рядки після ручного перегляду
│       ├── rejected.csv            ← автоматично відкинуті
│       └── rejected_manual.csv     ← вручну відкинуті
│
├── db/
│   └── competitors.db              ← SQLite (генерується скриптами)
│
├── scripts/
│   │
│   │   ── КРОК 1: збір сирих даних ──
│   ├── website_scrapers/           ← скрейпери власних сайтів (один файл на бренд)
│   │   ├── playwright_base.py      ← базовий клас для Playwright-скрейперів
│   │   ├── template_scraper.py     ← шаблон для нового сайту
│   │   ├── ryze_scraper.py
│   │   ├── mudwtr_scraper.py
│   │   └── ...                     ← інші бренди
│   │
│   ├── amazon scrapers/            ← Amazon-скрейпери (один файл на бренд)
│   │   ├── amazon_scraper_template.py
│   │   ├── ryze_amazon_scraper.py
│   │   └── ...                     ← інші бренди
│   │
│   │   ── КРОК 2: нормалізація та матчинг ──
│   ├── 04_filter_merge.py          ← об'єднати raw CSV, нормалізувати, відфільтрувати
│   ├── 05_assign_ids.py            ← присвоїти brand_id і product_id; виявити unmatched
│   ├── 06_fill_unmatched_ids.py    ← автоматично заповнити решту product_id
│   ├── 07_cleanup_ids.py           ← нормалізувати назви брендів і продуктів
│   ├── 08_fill_computed_fields.py  ← дорахувати serving_price і volume_g де можливо
│   │
│   │   ── КРОК 3: база даних ──
│   ├── 02_load_db.py               ← завантажити processed CSV → db/competitors.db
│   │
│   │   ── КРОК 4: аналіз ──
│   ├── 03_queries.sql              ← 10 аналітичних SQL-запитів
│   │
│   │   ── УТИЛІТИ ──
│   ├── patch_brand.py              ← замінити дані одного бренду без повного перезапуску
│   ├── shopify_scraper_template.py ← шаблон для Shopify-сайтів
│   └── [rerun scripts]             ← laird_rerun_*, ryze_rerun_*, foursigmatic_rerun_*
│
└── outputs/
    └── analysis_summary_ua.md     ← фінальний аналіз з висновками
```

### Як запустити

```bash
# 1. Встановити залежності
pip install -r requirements.txt
playwright install chromium

# 2. Зібрати дані (запускати кожен скрейпер окремо)
python scripts/website_scrapers/ryze_scraper.py
python scripts/amazon\ scrapers/ryze_amazon_scraper.py
# ... і так для кожного бренду
# Вихід: data/raw/{brand}_individual.csv та data/raw/{brand}_amazon.csv

# 3. Нормалізація та матчинг
python scripts/04_filter_merge.py
python scripts/05_assign_ids.py
python scripts/06_fill_unmatched_ids.py
# !! Тут: вручну перевірити data/processed/unmatched_review.csv !!
python scripts/07_cleanup_ids.py
python scripts/08_fill_computed_fields.py

# 4. Завантажити в базу даних
python scripts/02_load_db.py
# Вихід: db/competitors.db

# 5. Запустити аналітичні запити
# Через Python:
python -c "
import sqlite3
conn = sqlite3.connect('db/competitors.db')
# ... запити
"
# Або через sqlite3 CLI (якщо встановлений):
sqlite3 db/competitors.db < scripts/03_queries.sql
```

---

## SQL-запити: за що відповідає кожен

Всі запити знаходяться в `scripts/03_queries.sql` і є незалежними (можна запускати в довільному порядку).

### Цінові запити (Q1–Q3): позиціонування на ринку

**Q1 — Середня ціна за грам по брендах (до знижок)**
Показує, де бренд позиціонує себе цінністно — це якірна ціна, яку покупець бачить як "повну вартість". Використовує лише рядки з `volume_g > 0` (573 з 960).

**Q2 — Ефективна ціна за грам після знижок**
Реальна ціна транзакції — що покупець фактично платить. Для брендів з постійними знижками (Four Sigmatic 83.6% SKU) це і є ринкова ціна.

**Q3 — Перцентильний ранг HabitONE**
Де HabitONE стоїть відносно всіх 23 брендів за $/г. Результат: 68-й перцентиль ($0.185/г). Контекст: у peer set фокусованих брендів — 4-й з 7 (середина).

### Знижки (Q4, Q9): агресивність цінової стратегії

**Q4 — Частка SKU зі знижкою по брендах**
Показує, хто використовує знижки як постійну модель (Four Sigmatic 83.6%, MudWtr 73.3%) vs хто тримає чисте ціноутворення (North Spore 0%). Для HabitONE: 61.3% рядків зі знижкою.

**Q9 — Глибина знижки на підписку**
Порівнює середню single-ціну та sub-ціну по бренду. Виявляє, наскільки великий розрив між "першою покупкою" та "постійним покупцем". HabitONE: 37.1% — найбільший в датасеті, вдвічі більше за Ryze (18.2%).

### Каталог і формати (Q5, Q6, Q10): глибина асортименту

**Q5 — Кількість SKU за брендом і форматом**
Карта глибини каталогу: скільки продуктів кожного формату є у кожного бренду. Основа для виявлення прогалин.

**Q6 — Формати, яких немає у HabitONE**
Які формати пропонують конкуренти, але не HabitONE. Результат: `capsule`, `ground`, `packet`, `pods`. Packets — найпоширеніша прогалина (7 конкурентів).

**Q10 — Загальна кількість продуктів і рядків цін по брендах**
Загальна ширина каталогу. HabitONE: 5 продуктів, 31 рядок цін.

### Канальна динаміка (Q7, Q8): ціна за порцію та Amazon vs сайт

**Q7 — Середня ціна за порцію по брендах**
Найширший метрик: 795 рядків (vs 573 для $/г). Більш надійний для міжбрендового порівняння, бо не залежить від `volume_g`. HabitONE: $1.28/порцію — 2-й найдешевший у peer set.

**Q8 — Розрив між Amazon і власним сайтом**
Для брендів, що присутні в обох каналах: яка різниця середніх цін? HabitONE: -$46.72 (Amazon дешевше). Clevr і MudWtr — аутлайєри: Amazon дорожче (+$9.69 і +$9.66), бо вони використовують власний сайт як дисконтний канал підписки.

---

## Методологія аналізу

### Чому дві метрики ціни ($/г і $/порцію)

Ціна за грам (`Q1`) відповідає на питання "як бренд позиціонує свою вартість". Ціна за порцію (`Q7`) відповідає на питання "що платить покупець за одне приготування". Вони відрізняються через варіацію щільності продукту: кремер Clevr має більший об'єм при меншій щільності, тому виглядає дешевим за $/г, але дорогим за порцію. Обидві метрики потрібні разом.

### Чому порівнювати ціни до і після знижок

Ціна до знижки — це якір, що формує сприйняту цінність. Ціна після — реальна вартість транзакції. Якщо дивитись тільки на ефективну ціну, неможливо відрізнити "дешевий бренд" від "дорогого бренду, що завжди на розпродажі". Four Sigmatic — яскравий приклад другого.

### Чому два рівні порівняння (весь ринок vs peer set)

Повний ринок включає commodity Amazon-бренди (Bunkell, Taoters) і зрілі широкі бренди (Four Sigmatic, Laird), що не конкурують з HabitONE напряму. 68-й перцентиль на повному ринку — це статистичний факт, але не операційний орієнтир. Peer set (Everyday Dose, Shroomi, MudWtr, Ryze, IQBAR, Clevr) — це бренди з порівнянною моделлю, аудиторією та рівнем зрілості. Всередині peer set HabitONE — 4-й з 7 за $/г і 2-й з 7 за ціною порції.

### Відомі обмеження даних

- ~387/960 рядків не мають `volume_g` (pods-формат, частина Amazon-SKU). Q1–Q3 їх виключають.
- Laird Superfood (126 рядків) та Ryze (22 рядки) структурно не мають `serving_price` — скрейпери не зібрали `serving_count`.
- Amazon-native бренди (Bunkell, Taoters, YEGE, VenturePal, Lucid) мають commodity-ціноутворення і слабкий брендинг — $/г цих брендів не можна порівнювати з DTC-конкурентами напряму.
- Ціни зібрані в один часовий проміжок (20–25 травня 2026 р.). Промо-вікна можуть спотворювати результати.
- Кілька брендів мають дуже мало рядків: North Spore (1), Lucid (2), Pella (3), YEGE (3), Nootrum (3) — висновки по них лише орієнтовні.
