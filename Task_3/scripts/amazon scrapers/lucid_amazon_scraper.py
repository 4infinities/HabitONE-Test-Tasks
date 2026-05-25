#!/usr/bin/env python3
"""
lucid_amazon_scraper.py
Scrapes all Lucid (Super Coffee) products from their Amazon storefront.
Output: data/raw/lucid_amazon.csv

Usage:
  python "scripts/amazon scrapers/lucid_amazon_scraper.py"           # full run
  python "scripts/amazon scrapers/lucid_amazon_scraper.py" --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class LucidScraper(AmazonScraperBase):
    BRAND          = "Lucid"
    SEED_ASIN      = "B0DDY9GDNQ"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/LucidSuperCoffee/page/1AC95D1B-CDCE-4400-8388-21CF97132D3B"
    )
    OUT_FILENAME   = "lucid_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "packet":  ["packet", "sachet", "single serve", "stick pack", "stick"],
        "ground":  ["ground coffee", "ground beans", "whole bean", "brew", "drip", "french press"],
        "instant": ["instant", "powder", "powdered", "mix", "super coffee"],
        "pods":    ["k-cup", "kcup", "keurig", "pod"],
    }

    EXTRA_INGREDIENT_KW = {
        "lion's mane":      ["lion's mane", "lion mane"],
        "alpha-gpc":        ["alpha-gpc", "alpha gpc", "alphagpc"],
        "l-theanine":       ["l-theanine", "theanine"],
        "nootropic blend":  ["nootropic", "cognitive", "focus blend", "brain"],
        "mushroom blend":   ["mushroom blend", "mushroom complex", "mushroom"],
        "adaptogen":        ["adaptogen", "ashwagandha", "rhodiola"],
        "mct":              ["mct"],
        "collagen":         ["collagen"],
    }


if __name__ == "__main__":
    LucidScraper().run(pilot="--pilot" in sys.argv)
