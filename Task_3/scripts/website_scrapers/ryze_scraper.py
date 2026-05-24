#!/usr/bin/env python3
"""
ryze_scraper.py — Ryze Superfoods own-site scraper (ryzesuperfoods.com).
Strategy: Shopify JSON API (/products.json).
Subscription: ReCharge — two-tier discounts per product via /products/{handle}.js:
  price_adjustments[0] (order_count=1): first-order rate
  price_adjustments[1] (order_count=null): recurring rate  ← used here
If only one adjustment exists, that rate is used regardless of order_count.

Dark Roast and Medium Roast are separate handles (not Shopify variants).
Bundles (Starter Kit, Ritual Set) have format="bundle".
Output: data/raw/ryze_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase

import requests


class RyzeScraper(ShopifyScraperBase):
    BRAND          = "Ryze"
    BASE           = "https://www.ryzesuperfoods.com"
    COLLECTION     = "all"         # only used as fallback; overridden below
    OUT_FILENAME   = "ryze_individual.csv"
    DEFAULT_FORMAT = "instant"
    # SUB_DISCOUNT_PCT = None → auto-detect per product (varies: 20–50%)

    # Coffee product whitelist — only titles matching these keywords pass build_rows
    _COFFEE_KW = re.compile(
        r"coffee|dark roast|medium roast|bright blend|house blend"
        r"|starter kit|ritual (?:set|kit)|essentials kit|complete kit",
        re.IGNORECASE,
    )

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|-test$|test-product|^testing-"
        r"|gift-card|gift_card|sample|-trial|-free-|^free-"
        r"|3-month-upgrade|upgrade|-rebill$"
        r"|-month-plan$|-90-day-plan|-3-month-discount"
        r"|-special-pricing|-add-on-special|-otp$"
        r"|overnight-oats|acacia-|shipping-protection"
        r"|sticker$|copy-of-ryze-bundle|-gs$|-offer$"
        r"|matcha"
    )
    EXTRA_SKIP_KW = [
        "frother", "shaker", "mug", "tote", "gift card",
        "hoodie", "shirt", "hat", "poster", "sticker", "book",
        "matcha", "electrolyte", "overnight oats", "hot cocoa",
        "chicory", "chocolates", "probiotic creamer", "scoop",
        "spoon", "bracelet", "socks", "crewneck", "shipping protection",
        "magnet", "coasters", "rebill", "oos product", "reward sticker",
        "starter bag", "one-time offer", "chai", "cacao", "cocoa",
        "apparel", "bag clip", "month plan", "add-on", "oats",
    ]
    EXTRA_FORMAT_KW = {
        "bundle": ["starter kit", "ritual set", "ritual kit", "essentials kit", "complete kit"],
    }

    _BUNDLE_KW = ("starter kit", "ritual set", "ritual kit", "essentials kit",
                  "complete kit", "bundle", "duo", "gift set")

    def infer_format(self, title: str) -> str:
        t = title.lower()
        if any(kw in t for kw in self._BUNDLE_KW):
            return "bundle"
        if "carton" in t:
            return "rtd"
        return super().infer_format(title)

    # ── Coffee-only whitelist filter ──

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        title = product.get("title", "")
        if not self._COFFEE_KW.search(title):
            print(f"    SKIP (non-coffee): {title}")
            return []
        return super().build_rows(handle, product, session)

    # ── Handles via /products.json (Ryze uses custom theme, no /collections/all) ──

    def get_handles(self, session: requests.Session) -> list[str]:
        handles: list[str] = []
        page_num = 1
        while True:
            url = f"{self.BASE}/products.json?limit=250&page={page_num}"
            try:
                r = session.get(url, timeout=15)
                if r.status_code != 200:
                    self.log.error("products.json page=%d status=%d", page_num, r.status_code)
                    break
                products = r.json().get("products", [])
                if not products:
                    break
                for p in products:
                    h = p.get("handle", "")
                    if h and not self.SKIP_HANDLE_RE.search(h):
                        handles.append(h)
                if len(products) < 250:
                    break
                page_num += 1
            except Exception as e:
                self.log.error("products.json page=%d: %s", page_num, e)
                break
        return list(dict.fromkeys(handles))

    # ── Subscription via ReCharge: use recurring adjustment (order_count=None) ──

    def get_sub_pct(self, session: requests.Session, handle: str,
                    single_price: float | None = None) -> float | None:
        url = f"{self.BASE}/products/{handle}.js"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                return None
            groups = r.json().get("selling_plan_groups", [])
            if not groups:
                return None
            plans = groups[0].get("selling_plans", [])
            if not plans:
                return None
            adjustments = plans[0].get("price_adjustments", [])
            if not adjustments:
                return None

            # Prefer recurring adjustment (order_count=None) — steady-state sub price
            recurring = next(
                (a for a in adjustments
                 if a.get("order_count") is None and a.get("value_type") == "percentage"),
                None,
            )
            if recurring:
                pct = float(recurring["value"])
                return pct if pct > 0 else None

            # Single adjustment — use it if it's a non-zero percentage
            first = adjustments[0]
            if first.get("value_type") == "percentage":
                pct = float(first["value"])
                return pct if pct > 0 else None
        except Exception as e:
            self.log.error("product.js %s: %s", handle, e)
        return None


if __name__ == "__main__":
    RyzeScraper().run()
