#!/usr/bin/env python3
"""
strong_coffee_amazon_scraper.py
Scrapes all Strong Coffee Company products from their Amazon storefront.
Output: data/raw/strong_coffee_amazon.csv

Usage:
  python scripts/strong_coffee_amazon_scraper.py           # full run
  python scripts/strong_coffee_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class StrongCoffeeScraper(AmazonScraperBase):
    BRAND          = "Strong Coffee Company"
    SEED_ASIN      = "B0BHXKRW7Y"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/510FD03A-6834-40F4-A0BA-C2241D02CC60"
        "?ingress=2&lp_context_asin=B0BHXKRW7Y"
    )
    OUT_FILENAME   = "strong_coffee_amazon.csv"
    DEFAULT_FORMAT = "instant"


if __name__ == "__main__":
    StrongCoffeeScraper().run(pilot="--pilot" in sys.argv)
