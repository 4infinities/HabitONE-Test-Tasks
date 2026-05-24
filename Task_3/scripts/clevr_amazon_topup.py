#!/usr/bin/env python3
"""
clevr_amazon_topup.py
Fetches only the Clevr ASINs that failed in the main scraper run (rate-limited).
Appends rows to data/raw/clevr_amazon.csv — does not overwrite existing data.
"""

import csv
import time
import random
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from amazon_scraper_template import CSV_FIELDS, RAW_DIR
from clevr_amazon_scraper import ClevrScraper

OUT_FILE = RAW_DIR / "clevr_amazon.csv"

# ASINs that returned "No price found" in the main run
MISSING_ASINS = [
    "B0F8X8L5WF",  # Pistachio Matcha - 14 Lattes
    "B0GKGRKNBV",  # Strawberry Matcha - 14 Lattes
    "B0F67NZBGP",  # Chai - 30 Lattes
    "B0F67PJZ15",  # Matcha - 30 Lattes
    "B09H8944CG",  # Turmeric - 14 Lattes
    "B0C3K1G3RX",  # London Fog variant (unknown size)
    "B0C3JWSN8M",  # London Fog variant (unknown size)
    "B0C3JPT31F",  # London Fog variant (unknown size)
    "B0BF4FPM8W",  # London Fog variant (unknown size)
]


def main() -> None:
    scraper = ClevrScraper()
    rows = []

    for i, asin in enumerate(MISSING_ASINS, 1):
        url = f"https://www.amazon.com/dp/{asin}"
        scraper.safe_print(f"[{i}/{len(MISSING_ASINS)}] {url}")

        html = scraper.fetch_html(url)
        if not html:
            scraper.safe_print("  Failed to fetch — skipping.")
            continue

        detail = scraper.parse_product_page(html)
        if not detail or detail["single_price"] is None:
            scraper.safe_print("  No price found — skipping.")
            continue

        if scraper.is_merch(detail["title"]):
            scraper.safe_print(f"  Merch/skip: {detail['title'][:70]}")
            continue

        scraper.safe_print(f"  '{detail['title'][:70]}'")

        rows.append(scraper.build_row(detail, url, "single"))
        if detail["subscribe_available"]:
            rows.append(scraper.build_row(detail, url, "subscription"))

        if i < len(MISSING_ASINS):
            time.sleep(random.uniform(8, 14))

    if not rows:
        scraper.safe_print("No new rows collected.")
        return

    file_exists = OUT_FILE.exists()
    with open(OUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    scraper.safe_print(f"\nAppended {len(rows)} rows to {OUT_FILE}")


if __name__ == "__main__":
    main()
