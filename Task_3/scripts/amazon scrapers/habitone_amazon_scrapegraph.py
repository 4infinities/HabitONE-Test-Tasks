#!/usr/bin/env python3
"""
habitone_amazon_scrapegraph.py
Scrapes all HabitONE products from their Amazon storefront.
Output: data/raw/habitone_amazon_full.csv

Usage:
  python scripts/habitone_amazon_scrapegraph.py           # full run
  python scripts/habitone_amazon_scrapegraph.py --pilot   # seed ASIN only, no file written
"""

import sys
from amazon_scraper_template import AmazonScraperBase


class HabitoneAmazonScraper(AmazonScraperBase):
    BRAND          = "HabitONE"
    SEED_ASIN      = "B0FQP8H71L"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/3EB45754-1006-42A2-A2BD-4A8A66F2C432"
        "?ingress=2&lp_context_asin=B0FQP8H71L"
    )
    OUT_FILENAME   = "habitone_amazon_full.csv"
    DEFAULT_FORMAT = "instant"


if __name__ == "__main__":
    HabitoneAmazonScraper().run(pilot="--pilot" in sys.argv)
