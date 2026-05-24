#!/usr/bin/env python3
"""
la_republica_scraper.py — La Republica own-site scraper.
Strategy: Shopify JSON API. HTML returns PLN; JSON API returns USD.
Subscription: 15% off (user-confirmed: $93 → $79.05).
serving_size_g = 2.0g (confirmed: 70g / 35 servings), instant only.
volume_g from oz/lbs in title for ground bags; falls back to serving_count × 2.0 for instant.
Output: data/raw/la_republica_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests


class LaRepublicaScraper(ShopifyScraperBase):
    BRAND            = "La Republica"
    BASE             = "https://larepublicasuperfoods.com"
    COLLECTION       = "mushroom-coffee"
    OUT_FILENAME     = "la_republica_individual.csv"
    DEFAULT_FORMAT   = "instant"
    SUB_DISCOUNT_PCT = 15.0
    SERVING_SIZE_G   = 2.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|gift-card|gift_card|sample-pack|variety-pack"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "tote", "mug", "glass", "tumbler",
        "sticker", "poster", "hoodie", "t-shirt", "hat", "spoon", "scoop",
    ]

    def extract_volume_g(self, title: str, body: str = "") -> float | None:
        m = re.search(r"(\d+\.?\d*)\s*oz\b", title, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 28.3495, 1)
        m = re.search(r"(\d+\.?\d*)\s*lbs?\b", title, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 453.592, 1)
        return None

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
        serving_count = self.extract_serving_count(title, body)
        product_url   = f"{self.BASE}/products/{handle}"

        # physical label (oz/lbs) takes priority; instant falls back to serving_count × 2.0g
        volume_g = self.extract_volume_g(title)
        serving_size_g = None
        if volume_g is None and fmt == "instant" and serving_count:
            volume_g = round(serving_count * self.SERVING_SIZE_G, 1)
        if fmt == "instant" and serving_count:
            serving_size_g = self.SERVING_SIZE_G

        sp = round(single_price / serving_count, 2) if serving_count else None
        rows = [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=single_price, discount_pct=0,
            serving_price=sp, url=product_url, purchase_type="single",
        )]

        sub_price = round(single_price * (1 - self.SUB_DISCOUNT_PCT / 100), 2)
        sp_sub = round(sub_price / serving_count, 2) if serving_count else None
        rows.append(self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=sub_price, discount_pct=self.SUB_DISCOUNT_PCT,
            serving_price=sp_sub, url=product_url, purchase_type="subscription",
        ))
        return rows


if __name__ == "__main__":
    LaRepublicaScraper().run()
