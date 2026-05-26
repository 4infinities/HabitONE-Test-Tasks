# Database Schema — competitors.db

База даних SQLite, яку генерує `scripts/02_load_db.py` з оброблених CSV-файлів.

---

## Таблиці

### `brands`
Довідник брендів. Один рядок на бренд.

| Колонка | Тип | Примітки |
|---|---|---|
| `id` | INTEGER PK | Авто-інкремент |
| `name` | TEXT UNIQUE | Назва бренду (напр. "Four Sigmatic") |
| `website` | TEXT | Основний сайт |
| `channel` | TEXT | Основний канал продажів: `own_site` / `amazon` / `ebay` / `mixed` |
| `country` | TEXT | Завжди `US` |
| `is_habitone` | INTEGER | `1` тільки для HabitONE; використовується як фільтр у запитах |

```sql
CREATE TABLE brands (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    website     TEXT,
    channel     TEXT,
    country     TEXT DEFAULT 'US',
    is_habitone INTEGER DEFAULT 0
);
```

---

### `products`
Каталог продуктів. Один рядок на SKU (конкретний продукт).

| Колонка | Тип | Примітки |
|---|---|---|
| `id` | INTEGER PK | Авто-інкремент |
| `brand_id` | INTEGER FK → `brands.id` | Якому бренду належить продукт |
| `name` | TEXT | Назва продукту як на сайті |
| `format` | TEXT | Формат: `instant`, `packet`, `ground`, `capsule`, `rtd`, `pods`, `creamer`, `other` |
| `serving_size_g` | REAL | Грамів в одній порції; NULL якщо не знайдено |
| `serving_count` | INTEGER | Кількість порцій в упаковці; NULL якщо не знайдено |
| `key_ingredient` | TEXT | Головний функціональний інгредієнт (напр. "lion's mane") |

```sql
CREATE TABLE products (
    id              INTEGER PRIMARY KEY,
    brand_id        INTEGER NOT NULL REFERENCES brands(id),
    name            TEXT NOT NULL,
    format          TEXT,
    serving_size_g  REAL,
    serving_count   INTEGER,
    key_ingredient  TEXT
);
```

---

### `prices`
Цінові рядки. Один рядок на канал × тип покупки × дату збору.
У одного продукту може бути кілька рядків (own\_site + amazon, single + subscription).

| Колонка | Тип | Примітки |
|---|---|---|
| `id` | INTEGER PK | Авто-інкремент |
| `product_id` | INTEGER FK → `products.id` | До якого продукту відноситься ціна |
| `volume_g` | REAL | Загальна вага упаковки = `serving_size_g × serving_count` |
| `price_usd` | REAL | Відображувана ціна (після знижки, якщо знижка застосована на сайті) |
| `discount_pct` | REAL | Відсоток знижки з сайту; `0` якщо знижки немає |
| `serving_price` | REAL | Ціна за порцію = `price_usd / serving_count`; береться зі сторінки або обчислюється |
| `purchase_type` | TEXT | `subscription` / `single` / NULL (якщо бренд без підписки) |
| `channel` | TEXT | `own_site` / `amazon` / `ebay` |
| `date_collected` | TEXT | Дата збору у форматі ISO 8601: `YYYY-MM-DD` |
| `source_url` | TEXT | URL джерела |

```sql
CREATE TABLE prices (
    id             INTEGER PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    volume_g       REAL NOT NULL,
    price_usd      REAL NOT NULL,
    discount_pct   REAL DEFAULT 0,
    serving_price  REAL,
    purchase_type  TEXT,
    channel        TEXT NOT NULL,
    date_collected TEXT NOT NULL,
    source_url     TEXT
);
```

---

## Зв'язки (ERD)

```
brands (1)
  └─── products (N)        brand_id → brands.id
         └─── prices (N)   product_id → products.id
```

- Один бренд → багато продуктів
- Один продукт → багато цінових рядків (різні канали, типи покупки, дати)

---

## Ключові поля для аналітики

| Завдання | Поля |
|---|---|
| Ціна за грам | `prices.price_usd / prices.volume_g` |
| Ціна за порцію | `prices.serving_price` або `prices.price_usd / products.serving_count` |
| Ефективна ціна (зі знижкою) | `prices.price_usd * (1 - prices.discount_pct / 100.0)` |
| Фільтр HabitONE | `brands.is_habitone = 1` |
| Глибина каталогу | `COUNT(DISTINCT products.id)` GROUP BY `brands.name` |
| Охоплення підпискою | `prices.purchase_type = 'subscription'` |

---

## Формат-таксономія (поле `products.format`)

| Значення | Опис |
|---|---|
| `instant` | Розсипний порошок у банці/пакеті, дозується ложкою |
| `packet` | Одноразові саше |
| `ground` | Мелена кава |
| `capsule` | Капсули або таблетки |
| `rtd` | Ready-to-drink (банки, пляшки) |
| `pods` | K-cup або інші поди |
| `creamer` | Функціональний кример |
| `other` | Все інше |
