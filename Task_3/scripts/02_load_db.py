#!/usr/bin/env python3
"""
02_load_db.py — Loads processed CSVs into db/competitors.db.

Reads from:
  data/processed/all_brands_ids.csv   (auto-matched rows)
  data/processed/unmatched_review.csv (manually reviewed + auto-filled rows)

Both files carry brand_id and product_id already assigned by
05_assign_ids.py + 06_fill_unmatched_ids.py — these are used directly.

Safe to re-run — drops and recreates all tables each time.
"""

import csv
import sqlite3
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH       = ROOT / "db" / "competitors.db"
DB_PATH.parent.mkdir(exist_ok=True)

SOURCES = [
    PROCESSED_DIR / "all_brands_ids.csv",
    PROCESSED_DIR / "unmatched_review.csv",
]

SCHEMA = """
CREATE TABLE brands (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    website     TEXT,
    country     TEXT DEFAULT 'US',
    is_habitone INTEGER DEFAULT 0
);

CREATE TABLE products (
    id              INTEGER PRIMARY KEY,
    brand_id        INTEGER NOT NULL REFERENCES brands(id),
    name            TEXT NOT NULL,
    format          TEXT,
    serving_size_g  REAL,
    serving_count   INTEGER,
    key_ingredient  TEXT
);

CREATE TABLE prices (
    id             INTEGER PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    volume_g       REAL,
    price_usd      REAL NOT NULL,
    discount_pct   REAL DEFAULT 0,
    serving_price  REAL,
    purchase_type  TEXT,
    channel        TEXT NOT NULL,
    date_collected TEXT NOT NULL,
    source_url     TEXT
);
"""

BRAND_META: dict[str, dict] = {
    "HabitONE":          {"website": "habitone.co",             "is_habitone": 1},
    "Four Sigmatic":     {"website": "foursigmatic.com",        "is_habitone": 0},
    "Ryze":              {"website": "ryzesuperfoods.com",      "is_habitone": 0},
    "MudWtr":            {"website": "mudwtr.com",              "is_habitone": 0},
    "Everyday Dose":     {"website": "everydaydose.com",        "is_habitone": 0},
    "Shroomi":           {"website": "drinkshroomi.com",        "is_habitone": 0},
    "Rasa":              {"website": "rasacoffee.com",          "is_habitone": 0},
    "Om Mushrooms":      {"website": "ommushrooms.com",         "is_habitone": 0},
    "BodyBrain Coffee":  {"website": "bodybraincoffee.com",     "is_habitone": 0},
    "IQJOE":             {"website": "eatiqbar.com",            "is_habitone": 0},
    "Clevr Blends":      {"website": "clevrblends.com",         "is_habitone": 0},
    "Strong Coffee Co.": {"website": "strongcoffeecompany.com", "is_habitone": 0},
    "La Republica":      {"website": "larepublicacoffee.com",   "is_habitone": 0},
    "Renude":            {"website": "drinkrenude.com",         "is_habitone": 0},
    "North Spore":       {"website": "northspore.com",          "is_habitone": 0},
    "Nootrum":           {"website": "nootrum.com",             "is_habitone": 0},
    "Pella Nutrition":   {"website": "mypellanutrition.com",    "is_habitone": 0},
    "Laird Superfood":   {"website": "lairdsuper.com",          "is_habitone": 0},
    "Max Fit Wellness":  {"website": "maxfitwellness.com",      "is_habitone": 0},
    "Bunkell":           {"website": "amazon.com",              "is_habitone": 0},
    "Taoters":           {"website": "amazon.com",              "is_habitone": 0},
}


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def _float(val: str) -> float | None:
    try:
        return float(val) if val and val.strip() else None
    except ValueError:
        return None


def _int(val: str) -> int | None:
    try:
        return int(float(val)) if val and val.strip() else None
    except ValueError:
        return None


def load_all(conn: sqlite3.Connection) -> tuple[int, int, int]:
    cur = conn.cursor()
    cur.executescript(
        "DROP TABLE IF EXISTS prices;"
        "DROP TABLE IF EXISTS products;"
        "DROP TABLE IF EXISTS brands;"
    )
    cur.executescript(SCHEMA)

    seen_brands:   dict[int, bool] = {}   # brand_id → inserted
    seen_products: dict[int, bool] = {}   # product_id → inserted
    product_serving_count: dict[int, int] = {}  # product_id → serving_count (for sp fallback)
    price_count = 0

    for source in SOURCES:
        sep = detect_sep(source)
        with open(source, encoding="utf-8", errors="replace") as f:
            rows = list(csv.DictReader(f, delimiter=sep))

        for row in rows:
            brand_id   = _int(row.get("brand_id", ""))
            product_id = _int(row.get("product_id", ""))
            brand_name = row.get("brand", "").strip()

            if not brand_id or not product_id or not brand_name:
                continue

            # Insert brand once
            if brand_id not in seen_brands:
                meta = BRAND_META.get(brand_name, {"website": None, "is_habitone": 0})
                cur.execute(
                    "INSERT OR IGNORE INTO brands (id, name, website, is_habitone) VALUES (?, ?, ?, ?)",
                    (brand_id, brand_name, meta["website"], meta["is_habitone"]),
                )
                seen_brands[brand_id] = True

            # Insert product once (use first-seen row for product attributes)
            if product_id not in seen_products:
                cur.execute(
                    """INSERT OR IGNORE INTO products
                       (id, brand_id, name, format, serving_size_g, serving_count, key_ingredient)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        product_id,
                        brand_id,
                        row.get("product_name", "").strip() or "Unknown",
                        row.get("format") or None,
                        _float(row.get("serving_size_g", "")),
                        _int(row.get("serving_count", "")),
                        row.get("key_ingredient") or None,
                    ),
                )
                seen_products[product_id] = True
                sc_val = _int(row.get("serving_count", ""))
                if sc_val and sc_val > 0:
                    product_serving_count[product_id] = sc_val

            price_usd = _float(row.get("price_usd", ""))
            if price_usd is None:
                continue

            serving_price = _float(row.get("serving_price", ""))
            # Fill serving_price from price_usd / serving_count if missing.
            # Use row-level sc first; fall back to product-level sc already stored.
            if serving_price is None:
                row_sc = _int(row.get("serving_count", ""))
                if not row_sc or row_sc <= 0:
                    row_sc = product_serving_count.get(product_id)
                if row_sc and row_sc > 0:
                    serving_price = round(price_usd / row_sc, 4)

            cur.execute(
                """INSERT INTO prices
                   (product_id, volume_g, price_usd, discount_pct, serving_price,
                    purchase_type, channel, date_collected, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product_id,
                    _float(row.get("volume_g", "")),
                    price_usd,
                    _float(row.get("discount_pct", "")) or 0.0,
                    serving_price,
                    row.get("purchase_type") or None,
                    row.get("channel") or "own_site",
                    row.get("date_collected") or "",
                    row.get("url") or None,
                ),
            )
            price_count += 1

    conn.commit()
    return len(seen_brands), len(seen_products), price_count


def main() -> None:
    for src in SOURCES:
        if not src.exists():
            print(f"ERROR: {src} not found. Run 05_assign_ids.py and 06_fill_unmatched_ids.py first.")
            return

    print(f"Loading into {DB_PATH.relative_to(ROOT)}")
    with sqlite3.connect(DB_PATH) as conn:
        brands, products, prices = load_all(conn)
    print(f"Done: {brands} brands, {products} products, {prices} price rows")


if __name__ == "__main__":
    main()
