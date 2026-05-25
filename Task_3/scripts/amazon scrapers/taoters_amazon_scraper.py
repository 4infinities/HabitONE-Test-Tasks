#!/usr/bin/env python3
"""
taoters_amazon_scraper.py
Scrapes all Taoters products from their Amazon storefront.
All products are listed on the main store page; size/flavor variants are
discovered via twister on each product page (handled by base class run() loop).
Output: data/raw/taoters_amazon.csv

Usage:
  python scripts/taoters_amazon_scraper.py           # full run
  python scripts/taoters_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class TaotersScraper(AmazonScraperBase):
    BRAND          = "Taoters"
    SEED_ASIN      = "B0DHPGMLXW"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/8B15A017-7DD1-417E-BB3E-75FFC3AD203A"
        "?ingress=2&lp_context_asin=B0DHPGMLXW"
    )
    OUT_FILENAME   = "taoters_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "capsule": ["capsule", "pill", "supplement"],
        "packet":  ["packet", "sachet", "single serve", "stick"],
        "instant": ["powder", "instant", "mushroom coffee", "blend"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["7 mushroom", "10 mushroom", "multi mushroom", "mushroom complex"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "adaptogen":      ["ashwagandha", "rhodiola", "adaptogen"],
    }


if __name__ == "__main__":
    TaotersScraper().run(pilot="--pilot" in sys.argv)
