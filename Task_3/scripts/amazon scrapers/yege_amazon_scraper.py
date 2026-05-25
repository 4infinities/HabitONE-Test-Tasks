#!/usr/bin/env python3
"""
yege_amazon_scraper.py
Scrapes all YEGE products from their Amazon storefront.
Catalog has two products; size/flavor variants are discovered via the
twister widget on each product page (handled by base class run() loop).
Output: data/raw/yege_amazon.csv

Usage:
  python "scripts/amazon scrapers/yege_amazon_scraper.py"           # full run
  python "scripts/amazon scrapers/yege_amazon_scraper.py" --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class YegeScraper(AmazonScraperBase):
    BRAND          = "YEGE"
    SEED_ASIN      = "B0DJSKQRPM"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/YEGE/page/830A063C-2F68-424D-8A57-33DD3A3912C6"
    )
    OUT_FILENAME   = "yege_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "capsule": ["capsule", "pill", "supplement"],
        "packet":  ["packet", "sachet", "single serve", "stick"],
        "instant": ["powder", "instant", "mushroom coffee", "blend"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["mushroom blend", "multi mushroom", "mushroom complex",
                           "10 mushroom", "7 mushroom", "6 mushroom"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "chaga":          ["chaga"],
        "reishi":         ["reishi"],
        "cordyceps":      ["cordyceps"],
        "adaptogen":      ["ashwagandha", "rhodiola", "adaptogen"],
    }


if __name__ == "__main__":
    YegeScraper().run(pilot="--pilot" in sys.argv)
