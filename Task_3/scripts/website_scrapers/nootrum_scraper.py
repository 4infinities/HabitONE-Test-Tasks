#!/usr/bin/env python3
"""
nootrum_scraper.py — Nootrum own-site scraper.
Strategy: Shopify JSON API. Only products with "coffee" in title collected.
Discount from compare_at_price (no subscription option).
Confirmed: instant = 1.8g/serving, 54g / 30 servings.
Output: data/raw/nootrum_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests

SERVING_SIZE_INSTANT = 1.8  # confirmed: 54g / 30 servings


class NootrumScraper(ShopifyScraperBase):
    BRAND          = "Nootrum"
    BASE           = "https://nootrum.com"
    COLLECTION     = "all"
    OUT_FILENAME   = "nootrum_individual.csv"
    DEFAULT_FORMAT = "ground"

    SKIP_HANDLE_RE = re.compile(r"^[a-z0-9]{8,12}$|-test$")
    EXTRA_SKIP_KW  = [
        "frother", "shaker", "tote", "mug", "glass", "tumbler",
        "sticker", "planner", "poster", "magnet", "plushy", "spoon",
        "gift card", "hoodie",
    ]

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        title    = product.get("title", "")
        body_raw = product.get("body_html") or ""
        body     = re.sub(r"<[^>]+>", " ", body_raw)

        if self.is_skip(title):
            print(f"    SKIP: {title}")
            return []
        if "coffee" not in title.lower():
            print(f"    SKIP (non-coffee): {title}")
            return []

        variants = product.get("variants", [])
        if not variants:
            return []
        v = variants[0]
        price = float(v.get("price", "0") or 0)
        if price <= 0:
            return []

        compare_at = v.get("compare_at_price")
        compare_at = float(compare_at) if compare_at else None
        discount_pct = round((compare_at - price) / compare_at * 100, 1) if (compare_at and compare_at > price) else 0.0

        fmt        = self.infer_format(title)
        ingredient = self.infer_ingredient(title, body)
        product_url = f"{self.BASE}/products/{handle}"

        if fmt == "instant":
            serving_count  = self.extract_serving_count(body) or 30
            serving_size_g = SERVING_SIZE_INSTANT
            volume_g       = 54.0  # 30 × 1.8g, confirmed
        else:
            serving_count  = self.extract_serving_count(title, body)
            serving_size_g = None
            m = re.search(r"(\d+\.?\d*)\s*oz\b", title, re.IGNORECASE)
            volume_g = round(float(m.group(1)) * 28.3495, 1) if m else None

        sp = round(price / serving_count, 2) if serving_count else None
        return [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=price, discount_pct=discount_pct,
            serving_price=sp, url=product_url, purchase_type="single",
        )]


if __name__ == "__main__":
    NootrumScraper().run()
