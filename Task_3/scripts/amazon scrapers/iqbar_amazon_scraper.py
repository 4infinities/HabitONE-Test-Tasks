#!/usr/bin/env python3
"""
iqbar_amazon_scraper.py
Scrapes IQBAR Amazon storefront (single page, all products linked directly).
Output: data/raw/iqbar_amazon.csv

Usage:
  python scripts/iqbar_amazon_scraper.py           # full run
  python scripts/iqbar_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class IQBarScraper(AmazonScraperBase):
    BRAND          = "IQBAR"
    SEED_ASIN      = "B0C6S9SLRL"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/9EB06A38-ECFE-4630-986A-7CD00E97BECC"
        "?ingress=2&lp_context_asin=B0C6S9SLRL"
    )
    OUT_FILENAME   = "iqbar_amazon.csv"
    DEFAULT_FORMAT = "packet"  # IQJOE products are stick packs

    EXTRA_FORMAT_KW = {
        "packet": ["stick", "sticks", "iqjoe"],
        "instant": ["instant", "powder"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "shaker", "protein bar", "bar ", "keto bar",
    ]


if __name__ == "__main__":
    IQBarScraper().run(pilot="--pilot" in sys.argv)
