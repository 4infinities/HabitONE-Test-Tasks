#!/usr/bin/env python3
"""
ryze_amazon_scraper.py
Scrapes all Ryze products from their Amazon storefront.
All products are listed on the main store page; size/flavor variants are
discovered via twister on each product page (handled by base class run() loop).
Output: data/raw/ryze_amazon.csv

Usage:
  python scripts/ryze_amazon_scraper.py           # full run
  python scripts/ryze_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class RyzeScraper(AmazonScraperBase):
    BRAND          = "Ryze"
    SEED_ASIN      = "B0FSGHP1FC"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/F7EFEADF-7451-4022-AF90-6146779EEF12"
        "?ingress=2&lp_context_asin=B0FSGHP1FC"
    )
    OUT_FILENAME   = "ryze_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "packet":  ["packet", "sachet", "single serve", "stick"],
        "instant": ["powder", "instant", "mushroom coffee", "blend"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["6 mushroom", "7 mushroom", "mushroom blend", "mushroom complex", "mushroom"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "cordyceps":      ["cordyceps"],
        "reishi":         ["reishi"],
    }


if __name__ == "__main__":
    RyzeScraper().run(pilot="--pilot" in sys.argv)
