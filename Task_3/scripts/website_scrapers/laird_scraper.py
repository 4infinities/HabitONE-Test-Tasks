#!/usr/bin/env python3
"""
laird_scraper.py — Laird Superfood own-site scraper.
Strategy: Shopify JSON API. Multi-variant (8 oz / 1 lb / 2 lb / 3 lb) → separate rows.
Subscription: 20% off (confirmed from Sweet & Creamy Adaptogens reference, 2026-05-23).
volume_g from variant option values; serving_size_g from body nutrition label.
Output: data/raw/laird_individual.csv
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests

OZ_TO_G = 28.3495
LB_TO_G = 453.592


def _volume_from_option(opt: str) -> float | None:
    """Parse Laird variant option → total grams. Handles 'N Pack - Xoz' multi-pack format."""
    opt = opt.lower().strip()
    m = re.match(r"(\d+)\s*(?:pack)?\s*-\s*(\d+(?:\.\d+)?)\s*oz\b", opt)
    if m:
        return round(int(m.group(1)) * float(m.group(2)) * OZ_TO_G, 1)
    m = re.search(r"(\d+(?:\.\d+)?)\s*g\b", opt)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*lb\b", opt)
    if m:
        return round(float(m.group(1)) * LB_TO_G, 1)
    m = re.search(r"(\d+(?:\.\d+)?)\s*oz\b", opt)
    if m:
        return round(float(m.group(1)) * OZ_TO_G, 1)
    return None


class LairdScraper(ShopifyScraperBase):
    BRAND            = "Laird Superfood"
    BASE             = "https://lairdsuperfood.com"
    COLLECTION       = "all"
    OUT_FILENAME     = "laird_individual.csv"
    DEFAULT_FORMAT   = "instant"
    SUB_DISCOUNT_PCT = 20.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|-copy$|-copy-\d+$|-alt$|-broker$|^savedby"
        r"|sustainability-coverage|green-shipping|chose-any"
        r"|boomdizzle|mint-condition$|moroccan-your-world|marathon-maple"
        r"|need-for-seed|mega-nuts|fudge-nuts|peanut-chocolate-champ"
        r"|picky-full-steam|how-bout-dem-apples|trail-mix-fix"
        r"|calm-relax-mushrooms|focus-and-memory-mushrooms|sleep-recover"
        r"|performance-mushrooms|organic-lions-mane-mushroom-powder"
        r"|organic-oyster-mushroom-powder|organic-reishi-mushroom-powder"
        r"|organic-turkey-tail-mushroom-powder|peruvian|organic-fair-trade"
    )
    EXTRA_SKIP_KW = [
        "mug", "tumbler", "tote", "shaker", "frother", "blender bottle", "bag clip",
        "gift card", "hoodie", "hat", "shirt", "apparel", "sticker", "book", "cookbook",
        "hydrate", "electrolyte", "daily greens", "reds & greens", "greens powder",
        "spirulina", "protein bar", "energy bar", "snack bar", "nutrition bar",
        "superfood bar", "nut butter", "almond butter", "cashew butter",
        "kettle corn", "cracker", "chip", "collagen peptides", "omega",
        "vitamin d", "oatmeal", "daily reds", "matcha",
    ]
    EXTRA_FORMAT_KW = {
        "pods":    ["k-cup", "k cup", "kcup"],
        "creamer": ["creamer", "creme"],
        "instant": ["instant coffee", "latte mix", "instant latte"],
    }

    def _serving_size_from_body(self, body: str) -> float | None:
        for pat in [
            r"serving size[^<\n]{0,30}?(\d+(?:\.\d+)?)\s*g\b",
            r"per serving[^<\n]{0,30}?(\d+(?:\.\d+)?)\s*g\b",
            r"(\d+(?:\.\d+)?)\s*g\s*per serving",
        ]:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if 1 <= val <= 100:
                    return val
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

        fmt            = self.infer_format(title)
        ingredient     = self.infer_ingredient(title, body)
        serving_size_g = self._serving_size_from_body(body)
        sc_body        = self.extract_serving_count(title, body)
        product_url    = f"{self.BASE}/products/{handle}"
        rows = []

        for v in variants:
            price = float(v.get("price", 0) or 0)
            if price <= 0:
                continue

            # volume from variant option values (oz/lb patterns)
            volume_g = None
            for key in ("option1", "option2", "option3"):
                volume_g = _volume_from_option(v.get(key) or "")
                if volume_g:
                    break

            serving_count = sc_body
            if not serving_count and serving_size_g and volume_g:
                serving_count = round(volume_g / serving_size_g)

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

    def get_product(self, session: requests.Session, handle: str) -> dict | None:
        """Overridden to add 429/503 retry logic with backoff."""
        url = f"{self.BASE}/products/{handle}.json"
        for attempt in range(3):
            try:
                r = session.get(url, timeout=15)
                if r.status_code == 200:
                    return r.json().get("product", {})
                if r.status_code in (429, 503):
                    wait = 60 * (attempt + 1)
                    print(f"    {r.status_code} — waiting {wait}s...")
                    time.sleep(wait)
                    continue
                self.log.error("product %s status=%d", handle, r.status_code)
                return None
            except Exception as e:
                self.log.error("product %s: %s", handle, e)
                return None
        self.log.error("product %s: gave up after retries", handle)
        return None


if __name__ == "__main__":
    LairdScraper().run()
