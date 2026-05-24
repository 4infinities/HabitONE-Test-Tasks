#!/usr/bin/env python3
"""
mudwtr_scraper.py — MudWtr own-site scraper.
Strategy: Shopify JSON API.
Site-wide automatic single discount of 15% (base_price → single_price).
Subscription: per-product adjustment from /products/{handle}.js on top of single_price.
sub_discount reported vs base_price.
serving_size_g = 5.0g (confirmed: 150g / 30 servings).
Output: data/raw/mudwtr_individual.csv
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests

SINGLE_DISCOUNT_PCT = 15.0   # confirmed site-wide: $50 base → $42.50


class MudWtrScraper(ShopifyScraperBase):
    BRAND          = "MudWtr"
    BASE           = "https://mudwtr.com"
    COLLECTION     = "shop"
    OUT_FILENAME   = "mudwtr_individual.csv"
    DEFAULT_FORMAT = "instant"
    SERVING_SIZE_G = 5.0

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|matcha|turmeric|-rest-|^rest-|-rest$"
        r"|frother|gift-card|-page$|test$|^b2b-"
        r"|hoodie|beanie|shirt|hat-|hat$|mug|shaker|cacao|newspaper|whip$"
        r"|raglan|cotton-cap"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "mug", "tumbler", "spoon",
        "gift card", "hoodie", "shirt", "hat", "beanie", "cap",
        "poster", "newspaper", "book",
        "matcha", "turmeric", ":rest", "sleep", "nighttime", "cacao",
    ]
    EXTRA_FORMAT_KW = {
        "creamer": ["creamy"],
    }
    EXTRA_HANDLES = [
        "coffee-30-serving",
        "coffee-90-serving",
    ]

    def _get_with_retry(self, session: requests.Session,
                        url: str, label: str) -> dict | None:
        for attempt in range(2):
            try:
                r = session.get(url, timeout=15)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 403:
                    if attempt == 0:
                        print(f"    403 on {label}, sleeping 35s...")
                        time.sleep(35)
                    else:
                        self.log.error("403 | %s", label)
                else:
                    self.log.error("HTTP %d | %s", r.status_code, label)
                    return None
            except requests.exceptions.JSONDecodeError:
                if attempt == 0:
                    print(f"    Bad JSON on {label}, sleeping 35s...")
                    time.sleep(35)
                else:
                    self.log.error("JSONDecodeError | %s", label)
                    return None
            except Exception as e:
                self.log.error("fetch %s: %s", label, e)
                return None
        return None

    def get_product(self, session: requests.Session, handle: str) -> dict | None:
        data = self._get_with_retry(
            session, f"{self.BASE}/products/{handle}.json", f"{handle}.json"
        )
        return data.get("product", {}) if data else None

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
        base_price = float((variants[0].get("price") or 0))
        if base_price <= 0:
            return []

        fmt           = self.infer_format(title)
        ingredient    = self.infer_ingredient(title, body)
        serving_count = self.extract_serving_count(title) or self.extract_serving_count(body)
        volume_g      = round(serving_count * self.SERVING_SIZE_G, 1) if serving_count else None
        product_url   = f"{self.BASE}/products/{handle}"

        single_price = round(base_price * (1 - SINGLE_DISCOUNT_PCT / 100), 2)
        sp_single = round(single_price / serving_count, 2) if serving_count else None
        rows = [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=self.SERVING_SIZE_G, serving_count=serving_count,
            volume_g=volume_g, price=single_price, discount_pct=SINGLE_DISCOUNT_PCT,
            serving_price=sp_single, url=product_url, purchase_type="single",
        )]
        print(f"    {title} | single={single_price} ({SINGLE_DISCOUNT_PCT}% off)")

        # sub adjustment is applied on top of single_price; discount reported vs base
        data = self._get_with_retry(session, f"{self.BASE}/products/{handle}.js", f"{handle}.js")
        if data:
            groups = data.get("selling_plan_groups", [])
            if groups:
                plans = (groups[0].get("selling_plans") or [{}])
                adj = (plans[0].get("price_adjustments") or [{}])[0]
                if adj.get("value_type") == "percentage":
                    adj_pct = float(adj["value"])
                    sub_price = round(single_price * (1 - adj_pct / 100), 2)
                    sub_discount = round((base_price - sub_price) / base_price * 100, 1)
                    sp_sub = round(sub_price / serving_count, 2) if serving_count else None
                    rows.append(self._make_row(
                        title=title, fmt=fmt, ingredient=ingredient,
                        serving_size_g=self.SERVING_SIZE_G, serving_count=serving_count,
                        volume_g=volume_g, price=sub_price, discount_pct=sub_discount,
                        serving_price=sp_sub, url=product_url, purchase_type="subscription",
                    ))

        return rows


if __name__ == "__main__":
    MudWtrScraper().run()
