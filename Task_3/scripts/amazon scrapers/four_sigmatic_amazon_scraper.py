#!/usr/bin/env python3
"""
four_sigmatic_amazon_scraper.py
Scrapes all Four Sigmatic products from their Amazon storefront,
including all catalog sub-pages.
Output: data/raw/four_sigmatic_amazon.csv

Usage:
  python "scripts/amazon scrapers/four_sigmatic_amazon_scraper.py"           # full run
  python "scripts/amazon scrapers/four_sigmatic_amazon_scraper.py" --pilot   # seed ASIN only
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class FourSigmaticScraper(AmazonScraperBase):
    BRAND          = "Four Sigmatic"
    SEED_ASIN      = "B0756D1D39"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/BFD5C04F-8BEE-465A-8B09-51EAD476D2DC"
    )
    OUT_FILENAME   = "four_sigmatic_amazon.csv"
    DEFAULT_FORMAT = "ground"

    EXTRA_FORMAT_KW = {
        "pods":   ["k-cup", "k cup", "kcup", "keurig", "nespresso"],
        "packet": ["latte mix", "chai latte", "cacao"],
    }

    EXTRA_INGREDIENT_KW = {
        "lion's mane":    ["lion's mane", "lion mane", "focus"],
        "chaga":          ["chaga", "gut health", "immune"],
        "reishi":         ["reishi", "sleep"],
        "mushroom blend": ["7 mushroom", "10 mushroom", "mushroom blend"],
        "adaptogen":      ["adaptogen", "ashwagandha"],
    }


if __name__ == "__main__":
    FourSigmaticScraper().run(pilot="--pilot" in sys.argv)
