#!/usr/bin/env python3
"""
om_mushrooms_scraper.py — Om Mushrooms own-site scraper.
Strategy: Shopify JSON API. Multi-variant (10-serve, 30-serve) → separate rows.
Subscription: 15% off (confirmed from Mushroom Morning Blend reference).
serving_size_g = 8g (confirmed from reference).
Output: data/raw/om_mushrooms_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests


class OmMushroomsScraper(ShopifyScraperBase):
    BRAND            = "Om Mushrooms"
    BASE             = "https://ommushrooms.com"
    COLLECTION       = "all"
    OUT_FILENAME     = "om_mushrooms_individual.csv"
    DEFAULT_FORMAT   = "instant"
    SUB_DISCOUNT_PCT = 15.0
    SERVING_SIZE_G   = 8.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|-broker$|-copy$|-copy-\d+$"
        r"|-alt$|-target$|^savedby"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "tote", "mug", "glass", "tumbler",
        "sticker", "planner", "poster", "magnet", "plushy", "spoon",
        "gift card", "hoodie", "sweats", "pill case", "order protection",
        "gummies", "gummy", "plant protein", "protein powder",
        "hot chocolate", "matcha", "organic mushroom powder", "for you + pet",
    ]

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

        fmt         = self.infer_format(title)
        ingredient  = self.infer_ingredient(title, body)
        product_url = f"{self.BASE}/products/{handle}"
        rows = []

        for v in variants:
            price = float(v.get("price", 0) or 0)
            if price <= 0:
                continue

            # serving count from variant option values first, then title/body
            serving_count = None
            for key in ("option1", "option2", "option3"):
                m = re.search(r"(\d+)\s*servings?", v.get(key) or "", re.IGNORECASE)
                if m:
                    val = int(m.group(1))
                    if 1 <= val <= 500:
                        serving_count = val
                        break
            if not serving_count:
                serving_count = self.extract_serving_count(title, body)

            volume_g = round(serving_count * self.SERVING_SIZE_G, 1) if (serving_count and self.SERVING_SIZE_G) else None
            sp = round(price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=self.SERVING_SIZE_G, serving_count=serving_count,
                volume_g=volume_g, price=price, discount_pct=0,
                serving_price=sp, url=product_url, purchase_type="single",
            ))

            sub_price = round(price * (1 - self.SUB_DISCOUNT_PCT / 100), 2)
            sp_sub = round(sub_price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=self.SERVING_SIZE_G, serving_count=serving_count,
                volume_g=volume_g, price=sub_price, discount_pct=self.SUB_DISCOUNT_PCT,
                serving_price=sp_sub, url=product_url, purchase_type="subscription",
            ))

        return rows


if __name__ == "__main__":
    OmMushroomsScraper().run()
