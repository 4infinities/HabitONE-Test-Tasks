#!/usr/bin/env python3
"""
shroomi_scraper.py — Shroomi own-site scraper.
Strategy: Shopify JSON API. All products are roasted ground coffee.
Subscription: 10% off (user-confirmed: $36.99 → $33.29).
volume_g from oz/lbs in product title.
Output: data/raw/shroomi_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase


class ShroomiScraper(ShopifyScraperBase):
    BRAND            = "Shroomi"
    BASE             = "https://www.shroomihealth.com"
    COLLECTION       = "functional-mushroom-coffee"
    OUT_FILENAME     = "shroomi_individual.csv"
    DEFAULT_FORMAT   = "ground"
    SUB_DISCOUNT_PCT = 10.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|gift-card|gift_card|bundle|kit"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "tote", "mug", "glass", "tumbler",
        "sticker", "poster", "hoodie", "t-shirt", "hat", "spoon", "scoop",
    ]
    EXTRA_FORMAT_KW = {
        "ground": ["roast"],
    }

    def extract_volume_g(self, title: str, body: str = "") -> float | None:
        m = re.search(r"(\d+\.?\d*)\s*oz\b", title, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 28.3495, 1)
        m = re.search(r"(\d+\.?\d*)\s*lbs?\b", title, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 453.592, 1)
        return None


if __name__ == "__main__":
    ShroomiScraper().run()
