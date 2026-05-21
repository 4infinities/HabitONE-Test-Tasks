#!/usr/bin/env python3
"""
02_load_db.py — Loads all CSVs from data/raw/ into db/competitors.db.

Safe to re-run — drops and recreates all tables each time.
amazon_manual.csv uses the same CSV schema and is loaded alongside brand CSVs.
"""

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "db" / "competitors.db"
DB_PATH.parent.mkdir(exist_ok=True)

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
    channel        TEXT NOT NULL,
    date_collected TEXT NOT NULL,
    source_url     TEXT
);
"""

BRAND_META: dict[str, dict] = {
    "HabitONE":          {"website": "habitone.co",              "is_habitone": 1},
    "Four Sigmatic":     {"website": "foursigmatic.com",         "is_habitone": 0},
    "Ryze":              {"website": "ryzesuperfoods.com",        "is_habitone": 0},
    "MudWtr":            {"website": "mudwtr.com",               "is_habitone": 0},
    "Everyday Dose":     {"website": "everydaydose.com",         "is_habitone": 0},
    "Shroomi":           {"website": "drinkshroomi.com",         "is_habitone": 0},
    "Rasa":              {"website": "rasacoffee.com",           "is_habitone": 0},
    "Om Mushrooms":      {"website": "ommushrooms.com",          "is_habitone": 0},
    "BodyBrain Coffee":  {"website": "bodybraincoffee.com",      "is_habitone": 0},
    "IQJOE":             {"website": "eatiqbar.com",             "is_habitone": 0},
    "Clevr Blends":      {"website": "clevrblends.com",          "is_habitone": 0},
    "Strong Coffee Co.": {"website": "strongcoffeecompany.com",  "is_habitone": 0},
    "La Republica":      {"website": "larepublicacoffee.com",    "is_habitone": 0},
    "Renude":            {"website": "drinkrenude.com",          "is_habitone": 0},
    "North Spore":       {"website": "northspore.com",           "is_habitone": 0},
    "Nootrum":           {"website": "nootrum.com",              "is_habitone": 0},
    "Pella Nutrition":   {"website": "mypellanutrition.com",     "is_habitone": 0},
}


def _float(val: str) -> float | None:
    try:
        return float(val) if val else None
    except ValueError:
        return None


def _int(val: str) -> int | None:
    try:
        return int(val) if val else None
    except ValueError:
        return None


def load_all(conn: sqlite3.Connection) -> tuple[int, int, int]:
    cur = conn.cursor()
    cur.executescript("DROP TABLE IF EXISTS prices; DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS brands;")
    cur.executescript(SCHEMA)

    brand_ids: dict[str, int] = {}
    product_ids: dict[tuple, int] = {}  # (brand_id, name) -> product.id
    price_count = 0

    for csv_path in sorted(RAW_DIR.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                brand_name = (row.get("brand") or "").strip()
                if not brand_name:
                    continue

                if brand_name not in brand_ids:
                    meta = BRAND_META.get(brand_name, {"website": None, "is_habitone": 0})
                    cur.execute(
                        "INSERT OR IGNORE INTO brands (name, website, is_habitone) VALUES (?, ?, ?)",
                        (brand_name, meta["website"], meta["is_habitone"]),
                    )
                    cur.execute("SELECT id FROM brands WHERE name = ?", (brand_name,))
                    brand_ids[brand_name] = cur.fetchone()[0]

                brand_id = brand_ids[brand_name]
                product_name = (row.get("product_name") or "").strip() or "Unknown"

                key = (brand_id, product_name)
                if key not in product_ids:
                    cur.execute(
                        """INSERT INTO products (brand_id, name, format, serving_size_g, serving_count, key_ingredient)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            brand_id,
                            product_name,
                            row.get("format") or None,
                            _float(row.get("serving_size_g", "")),
                            _int(row.get("serving_count", "")),
                            row.get("key_ingredient") or None,
                        ),
                    )
                    product_ids[key] = cur.lastrowid

                price_usd = _float(row.get("price_usd", ""))
                if price_usd is None:
                    continue

                cur.execute(
                    """INSERT INTO prices (product_id, volume_g, price_usd, discount_pct, channel, date_collected, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        product_ids[key],
                        _float(row.get("volume_g", "")),
                        price_usd,
                        _float(row.get("discount_pct", "")) or 0,
                        row.get("channel") or "own_site",
                        row.get("date_collected") or "",
                        row.get("url") or None,
                    ),
                )
                price_count += 1

    conn.commit()
    return len(brand_ids), len(product_ids), price_count


def main():
    csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSVs found in {RAW_DIR}. Run 01_scrape.py first.")
        return
    print(f"Loading {len(csv_files)} CSV(s) from data/raw/ into {DB_PATH.relative_to(ROOT)}")
    with sqlite3.connect(DB_PATH) as conn:
        brands, products, prices = load_all(conn)
    print(f"Done: {brands} brands, {products} products, {prices} price records")


if __name__ == "__main__":
    main()
