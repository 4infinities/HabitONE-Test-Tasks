#!/usr/bin/env python3
"""
clevr_amazon_scraper.py
Scrapes all Clevr Blends products from their Amazon storefront.
Output: data/raw/clevr_amazon.csv

Usage:
  python scripts/clevr_amazon_scraper.py           # full run
  python scripts/clevr_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from amazon_scraper_template import AmazonScraperBase


class ClevrScraper(AmazonScraperBase):
    BRAND          = "Clevr Blends"
    SEED_ASIN      = "B09JV6TT9C"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/Clevr/page/96F67E37-CB20-439D-A313-36E9C2CBB295"
        "?lp_asin=B09JV6TT9C&ref_=ast_bln"
    )
    OUT_FILENAME   = "clevr_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "instant": ["latte", "superlatte"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "kit", "bundle", "shaker",
    ]


if __name__ == "__main__":
    ClevrScraper().run(pilot="--pilot" in sys.argv)
