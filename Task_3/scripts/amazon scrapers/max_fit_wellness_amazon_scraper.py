#!/usr/bin/env python3
"""
max_fit_wellness_amazon_scraper.py
Max Fit Wellness has no brand store — all SKUs live as variants on one listing.
The twister on the seed product page exposes all variant ASINs automatically.
Output: data/raw/max_fit_wellness_amazon.csv

Usage:
  python scripts/max_fit_wellness_amazon_scraper.py           # full run
  python scripts/max_fit_wellness_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class MaxFitWellnessScraper(AmazonScraperBase):
    BRAND          = "Max Fit Wellness"
    SEED_ASIN      = "B0C8WGD562"
    # No brand store; use seed product page as the entry point
    STOREFRONT_URL = "https://www.amazon.com/dp/B0C8WGD562"
    OUT_FILENAME   = "max_fit_wellness_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["10 mushroom", "7 mushroom", "mushroom complex"],
    }

    def get_asins_from_storefront(self, _html: str) -> list[str]:
        # No brand store — start from seed; all variants discovered via twister
        return [self.SEED_ASIN]


if __name__ == "__main__":
    MaxFitWellnessScraper().run(pilot="--pilot" in sys.argv)
