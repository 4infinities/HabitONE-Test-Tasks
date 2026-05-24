#!/usr/bin/env python3
"""
laird_amazon_scraper.py
Scrapes Laird Superfood Amazon storefront (single page, full catalog linked directly).
Output: data/raw/laird_amazon.csv

Usage:
  python scripts/laird_amazon_scraper.py           # full run
  python scripts/laird_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from amazon_scraper_template import AmazonScraperBase


class LairdScraper(AmazonScraperBase):
    BRAND          = "Laird Superfood"
    SEED_ASIN      = "B088PB9B1L"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/LairdSuperfood/page/F859FC96-07C4-4ED8-952A-9CA41B8B784F"
        "?lp_asin=B088PB9B1L&ref_=ast_bln"
    )
    OUT_FILENAME   = "laird_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "creamer": ["creamer", "superfood creamer", "original creamer"],
        "instant": ["instafuel", "coffee", "latte"],
        "ground":  ["ground coffee"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "shaker", "hydrate", "hydration", "protein bar", "snack bar",
    ]


if __name__ == "__main__":
    LairdScraper().run(pilot="--pilot" in sys.argv)
