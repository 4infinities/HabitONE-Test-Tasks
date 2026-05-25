#!/usr/bin/env python3
"""
ryze_creamer_addon.py — appends Ryze creamer products to ryze_individual.csv.
Scrapes /collections/creamer, skips free/$0 and add-on/special-pricing handles,
deduplicates by normalized name before appending.
Run: python scripts/website_scrapers/ryze_creamer_addon.py
"""

import re
import csv
import time
import random
import requests
from datetime import date
from pathlib import Path

BASE     = "https://www.ryzesuperfoods.com"
OUT_FILE = Path(__file__).parent.parent.parent / "data" / "raw" / "ryze_individual.csv"
TODAY    = date.today().isoformat()

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

SKIP_RE = re.compile(
    r"^free-|^free\b|-add-on|-special-pricing|-offer$|-starter-bag"
    r"|^try-our|50-off|-rebill|-otp$|-add-on-og$"
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def norm(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    n = re.sub(r"\bserving\b", "servings", n)
    return re.sub(r" +", " ", n).strip()


def get_sub_pct(session: requests.Session, handle: str) -> float | None:
    r = session.get(f"{BASE}/products/{handle}.js", timeout=15)
    if r.status_code != 200:
        return None
    groups = r.json().get("selling_plan_groups", [])
    if not groups:
        return None
    plans = groups[0].get("selling_plans", [])
    if not plans:
        return None
    adjs = plans[0].get("price_adjustments", [])
    if not adjs:
        return None
    recurring = next(
        (a for a in adjs if a.get("order_count") is None and a.get("value_type") == "percentage"),
        None,
    )
    if recurring:
        v = float(recurring["value"])
        return v if v > 0 else None
    first = adjs[0]
    if first.get("value_type") == "percentage":
        v = float(first["value"])
        return v if v > 0 else None
    return None


def extract_serving_count(title: str) -> int | None:
    m = re.search(r"(\d+)\s*servings?", title, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return val if 1 <= val <= 500 else None
    return None


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    # Fetch collection
    r = session.get(f"{BASE}/collections/creamer/products.json?limit=250", timeout=15)
    r.raise_for_status()
    products = r.json().get("products", [])
    print(f"Collection products: {len(products)}")

    # Load existing names from file to skip already-present products
    existing_norms: set[str] = set()
    if OUT_FILE.exists():
        with OUT_FILE.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_norms.add(norm(row["product_name"]))

    new_rows: list[dict] = []
    seen_norms: set[str] = set()  # within this run

    for p in products:
        handle = p.get("handle", "")
        title  = p.get("title", "")

        if SKIP_RE.search(handle):
            print(f"  SKIP (handle): {handle}")
            continue

        variants = p.get("variants", [])
        if not variants:
            continue
        price = float(variants[0].get("price", 0) or 0)  # products.json returns dollars as string
        if price <= 0:
            print(f"  SKIP ($0): {title}")
            continue

        name_norm = norm(title)
        if name_norm in existing_norms or name_norm in seen_norms:
            print(f"  SKIP (dupe): {title}")
            continue

        serving_count = extract_serving_count(title)
        serving_price = round(price / serving_count, 2) if serving_count else None
        product_url   = f"{BASE}/products/{handle}"

        row_single = {
            "brand": "Ryze", "product_name": title, "format": "creamer",
            "serving_size_g": None, "serving_count": serving_count,
            "volume_g": None, "price_usd": price, "discount_pct": 0,
            "serving_price": serving_price, "key_ingredient": "mushroom",
            "channel": "own_site", "url": product_url,
            "date_collected": TODAY, "purchase_type": "single",
        }
        new_rows.append(row_single)
        seen_norms.add(name_norm)
        print(f"  + {title} | ${price} single")

        time.sleep(random.uniform(2, 4))
        sub_pct = get_sub_pct(session, handle)
        if sub_pct is not None:
            sub_price = round(price * (1 - sub_pct / 100), 2)
            sub_sp    = round(sub_price / serving_count, 2) if serving_count else None
            new_rows.append({**row_single,
                "price_usd": sub_price, "discount_pct": sub_pct,
                "serving_price": sub_sp, "purchase_type": "subscription",
            })
            print(f"    sub ${sub_price} ({sub_pct}% off)")

        time.sleep(random.uniform(2, 4))

    if not new_rows:
        print("Nothing new to append.")
        return

    with OUT_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerows(new_rows)

    print(f"\nAppended {len(new_rows)} rows to {OUT_FILE.name}")


if __name__ == "__main__":
    main()
