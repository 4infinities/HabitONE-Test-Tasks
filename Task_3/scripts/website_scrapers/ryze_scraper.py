#!/usr/bin/env python3
"""
ryze_scraper.py — Ryze Superfoods own-site scraper (ryzesuperfoods.com).
Strategy: Shopify collections JSON API.
Collections scraped:
  - /collections/main-cocoa-products (paginated until empty)
  - /collections/mushroom-coffee pages 1–4
Deduplication:
  - Primary: Shopify product ID across collections (prevents cross-collection dupes)
  - Secondary: (normalized title, serving_count, price_usd, purchase_type) on output rows
    (catches SEO-variant handles that map to the same product content)
Handles ending in -gs (e.g. mushroom-hot-cocoa-20-servings-gs) are skipped via SKIP_HANDLE_RE
  as they are URL-only SEO duplicates of canonical handles.
Subscription: ReCharge — recurring adjustment (order_count=None) preferred over first-order.
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
    COLLECTION     = "mushroom-coffee"   # used only for base-class display string
    OUT_FILENAME   = "ryze_individual.csv"
    DEFAULT_FORMAT = "instant"
    DEDUPLICATE    = True

    # Collections to scrape: (slug, page_range or None for auto-paginate)
    _COLLECTIONS = [
        ("main-cocoa-products", None),        # paginate until empty
        ("mushroom-coffee",     range(1, 5)), # pages 1–4 explicit
    ]

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
        "matcha", "electrolyte", "overnight oats",
        "chicory", "probiotic creamer", "scoop",
        "spoon", "bracelet", "socks", "crewneck", "shipping protection",
        "magnet", "coasters", "rebill", "oos product", "reward sticker",
        "starter bag", "one-time offer", "chai",
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

    def get_handles(self, session: requests.Session) -> list[str]:
        seen_ids: set[int] = set()
        handles: list[str] = []

        for collection, pages in self._COLLECTIONS:
            page_iter = range(1, 100) if pages is None else pages
            for page in page_iter:
                url = (
                    f"{self.BASE}/collections/{collection}"
                    f"/products.json?limit=250&page={page}"
                )
                try:
                    r = session.get(url, timeout=15)
                    if r.status_code != 200:
                        self.log.error(
                            "collection %s page=%d status=%d",
                            collection, page, r.status_code,
                        )
                        break
                    products = r.json().get("products", [])
                    if not products:
                        break
                    for p in products:
                        pid = p.get("id")
                        h = p.get("handle", "")
                        if not h or not pid:
                            continue
                        if self.SKIP_HANDLE_RE and self.SKIP_HANDLE_RE.search(h):
                            continue
                        if pid not in seen_ids:
                            seen_ids.add(pid)
                            handles.append(h)
                    # auto-paginate mode: stop when page is not full
                    if pages is None and len(products) < 250:
                        break
                except Exception as e:
                    self.log.error("collection %s page=%d: %s", collection, page, e)
                    break

        return handles

    def _dedup(self, rows: list[dict]) -> list[dict]:
        seen: set = set()
        out: list[dict] = []
        for row in rows:
            name = re.sub(r"\s+", " ", row["product_name"].lower().strip())
            key = (name, row["serving_count"], row["price_usd"], row["purchase_type"])
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out

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

            first = adjustments[0]
            if first.get("value_type") == "percentage":
                pct = float(first["value"])
                return pct if pct > 0 else None
        except Exception as e:
            self.log.error("product.js %s: %s", handle, e)
        return None


if __name__ == "__main__":
    RyzeScraper().run()
