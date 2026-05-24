#!/usr/bin/env python3
"""
bunkell_amazon_scraper.py
Scrapes all Bunkell products from their Amazon storefront.
All products are listed on the main store page; size variants are discovered
via twister on each product page (handled by base class run() loop).
Output: data/raw/bunkell_amazon.csv

Usage:
  python scripts/bunkell_amazon_scraper.py           # full run
  python scripts/bunkell_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from amazon_scraper_template import AmazonScraperBase


class BunkellScraper(AmazonScraperBase):
    BRAND          = "Bunkell"
    SEED_ASIN      = "B0DHP915W6"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/Bunkell/page/B897E152-7700-475F-84CF-C0D5716D8ECF"
        "?lp_asin=B0DHP915W6&ref_=ast_bln"
    )
    OUT_FILENAME   = "bunkell_amazon.csv"
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
    BunkellScraper().run(pilot="--pilot" in sys.argv)
