#!/usr/bin/env python3
"""
iqbar_scraper.py — Scraper for IQJOE products at eatiqbar.com/collections/iqjoe.

Output: data/raw/iqbar_individual.csv

Strategy: inherits ShopifyScraperBase (requests + Shopify JSON API).
  - HANDLE_FILTER = "iqjoe": skips bars, accessories, other collections
  - Subscription: per_delivery_price (USD cents) embedded in static page HTML
  - serving_count: "(N Sticks)" or "N-sticks" in title
  - volume_g: oz in body → grams; serving_size_g derived from volume / serving_count
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from shopify_scraper_template import ShopifyScraperBase

INGREDIENT_KEYWORDS = [
    "lion's mane", "lions mane", "magnesium l-threonate", "magnesium threonate",
    "l-theanine", "theanine", "chaga", "reishi", "cordyceps",
    "ashwagandha", "rhodiola", "adaptogen", "mushroom",
]


class IQBarScraper(ShopifyScraperBase):
    BRAND        = "IQBAR"
    BASE         = "https://www.eatiqbar.com"
    COLLECTION   = "iqjoe"
    OUT_FILENAME = "iqbar_individual.csv"
    DEFAULT_FORMAT = "instant"
    SKIP_HANDLE_RE = re.compile(r"^ultimate-sampler$")  # bars + sticks bundle, not coffee-only
    EXTRA_INGREDIENT_KW = INGREDIENT_KEYWORDS
    # Subscription: base get_sub_pct() uses product.js → selling_plan_groups (15%)

    # ── Custom parsers ─────────────────────────────────────────────────────

    def _parse_serving_count(self, text: str) -> int | None:
        for pat in [
            r"\((\d+)\s*sticks?\)",
            r"(\d+)[- ]sticks?",
            r"(\d+)\s*servings?",
            r"(\d+)\s*(?:count|ct)\b",
            r"(\d+)\s*packets?",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 500:
                    return val
        return None

    def _parse_volume_g(self, text: str) -> float | None:
        m = re.search(r"(\d+\.?\d*)\s*oz\b", text, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 28.3495, 1)
        m = re.search(r"(\d+\.?\d*)\s*g\b", text)
        if m:
            val = float(m.group(1))
            if 50 <= val <= 2000:
                return val
        return None

    # ── Row building ───────────────────────────────────────────────────────

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        title    = product.get("title", "")
        body_raw = product.get("body_html") or ""
        body     = re.sub(r"<[^>]+>", " ", body_raw)

        if self.is_skip(title):
            print(f"    SKIP: {title}")
            return []

        variants = product.get("variants", [])
        if not variants:
            return []

        single_price = float(variants[0].get("price", 0) or 0)
        if single_price <= 0:
            return []

        fmt           = self.infer_format(title)
        ingredient    = self.infer_ingredient(title, body)
        serving_count = self._parse_serving_count(title) or self._parse_serving_count(body)
        volume_g      = self._parse_volume_g(body)
        serving_size_g = round(volume_g / serving_count, 2) if (volume_g and serving_count) else None
        product_url   = f"{self.BASE}/products/{handle}"

        sp_single = round(single_price / serving_count, 2) if serving_count else None
        rows = [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=single_price, discount_pct=0,
            serving_price=sp_single, url=product_url, purchase_type="single",
        )]

        sub_pct = self.get_sub_pct(session, handle, single_price)
        if sub_pct is not None:
            sub_price = round(single_price * (1 - sub_pct / 100), 2)
            sp_sub    = round(sub_price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=sub_price, discount_pct=sub_pct,
                serving_price=sp_sub, url=product_url, purchase_type="subscription",
            ))

        return rows


if __name__ == "__main__":
    IQBarScraper().run()
