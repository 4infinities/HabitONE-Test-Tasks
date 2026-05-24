#!/usr/bin/env python3
"""
max_fit_wellness_scraper.py — Max Fit Wellness own-site scraper.
Strategy: Shopify JSON API. Multi-variant per product.
Subscription: 5% off (user-confirmed: $19.99 → $18.99).
volume_g and serving_count extracted from variant title, product title, body, handle.
Output: data/raw/max_fit_wellness_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests


def _extract_volume_g(*texts: str) -> float | None:
    for text in texts:
        m = re.search(r"(\d+\.?\d*)\s*oz\b", text, re.IGNORECASE)
        if m:
            val = round(float(m.group(1)) * 28.3495, 1)
            if 50 <= val <= 5000:
                return val
        m = re.search(r"(\d+\.?\d*)\s*lbs?\b", text, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * 453.592, 1)
    return None


def _extract_serving_count(*texts: str) -> int | None:
    for text in texts:
        for pat in [r"(\d+)\s*servings?", r"(\d+)\s*-\s*serving", r"(\d+)\s*count"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 500:
                    return val
    return None


class MaxFitWellnessScraper(ShopifyScraperBase):
    BRAND            = "Max Fit Wellness"
    BASE             = "https://www.maxfitwellness.com"
    COLLECTION       = "all"
    OUT_FILENAME     = "max_fit_wellness_individual.csv"
    DEFAULT_FORMAT   = "instant"
    SUB_DISCOUNT_PCT = 5.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|gift-card|gift_card|bundle|kit|sample-pack|sea-moss"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "tote", "mug", "glass", "tumbler",
        "sticker", "poster", "hoodie", "t-shirt", "hat", "spoon", "scoop",
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
        handle_text = handle.replace("-", " ")
        rows = []

        for v in variants:
            price = float(v.get("price", 0) or 0)
            if price <= 0:
                continue

            v_title = v.get("title", "Default Title")
            serving_count  = _extract_serving_count(v_title, title, body, handle_text)
            volume_g       = _extract_volume_g(v_title, title, body, handle_text)
            serving_size_g = round(volume_g / serving_count, 2) if (volume_g and serving_count) else None
            sp = round(price / serving_count, 2) if serving_count else None

            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=price, discount_pct=0,
                serving_price=sp, url=product_url, purchase_type="single",
            ))

            sub_price = round(price * (1 - self.SUB_DISCOUNT_PCT / 100), 2)
            sp_sub = round(sub_price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=sub_price, discount_pct=self.SUB_DISCOUNT_PCT,
                serving_price=sp_sub, url=product_url, purchase_type="subscription",
            ))

        return rows


if __name__ == "__main__":
    MaxFitWellnessScraper().run()
