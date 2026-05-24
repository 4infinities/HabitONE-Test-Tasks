#!/usr/bin/env python3
"""
shopify_scraper_template.py
Base class for HabitONE own-site Shopify scrapers (requests + JSON API, no Playwright).

Subclass config:
    BRAND            — brand display name
    BASE             — store root URL, no trailing slash
    COLLECTION       — Shopify collection slug ("all", "coffee", "iqjoe", …)
    OUT_FILENAME     — filename written to data/raw/
    DEFAULT_FORMAT   — fallback when no format keyword matches
    SUB_DISCOUNT_PCT — float → hardcoded sub % for all products; None → auto-detect via product.js
    SKIP_HANDLE_RE   — compiled re.Pattern (optional, brand-specific handle blocklist)
    HANDLE_FILTER    — string; if set, keep only handles that contain it (e.g. "iqjoe")
    EXTRA_FORMAT_KW  — dict merged on top of base format keywords
    EXTRA_INGREDIENT_KW — list appended to base ingredient keywords
    EXTRA_SKIP_KW    — list appended to base merch/non-coffee title blocklist
    EXTRA_HANDLES    — handles not in the collection but needed (added after pagination)
    DEDUPLICATE      — bool; if True, dedup rows by (serving_count, price_usd, purchase_type)

Subscription detection (in priority order):
  1. SUB_DISCOUNT_PCT set → apply that % to every product, no HTTP request needed
  2. /products/{handle}.js → selling_plan_groups[0].selling_plans[0]
        .price_adjustments[0] with value_type="percentage"
  3. Neither → no subscription row emitted
  Override get_sub_pct() in the subclass for brand-specific subscription widgets.
"""

import re
import csv
import time
import random
import logging
import requests
from datetime import date
from pathlib import Path

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

_BASE_FORMAT_KW: dict[str, list[str]] = {
    "packet":  ["packet", "sachet", "single-serve", "stick pack"],
    "capsule": ["capsule", "pill", "softgel"],
    "creamer": ["creamer", "creme"],
    "pods":    ["pod", "k-cup"],
    "ground":  ["ground coffee", "whole bean", "brew", "french press"],
    "instant": ["instant", "latte", "powder", "powdered"],
}

_BASE_INGREDIENT_KW: list[str] = [
    "lion's mane", "lions mane", "chaga", "reishi", "cordyceps", "turkey tail",
    "ashwagandha", "rhodiola", "l-theanine", "theanine", "tongkat ali",
    "collagen", "mushroom", "adaptogen", "nootropic",
]

_BASE_SKIP_KW: list[str] = [
    "shirt", " hat", "tote", "mug", "glass", "tumbler", "shorts", " tee",
    "crop top", "crew neck", "hoodie", "frother", "cowboy", "cowgirl",
    "gift card", "sticker", "poster", "planner", "gummies", "gummy",
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ShopifyScraperBase:
    # ── Required per-brand config ──────────────────────────────────────────
    BRAND: str         = ""
    BASE: str          = ""
    COLLECTION: str    = ""
    OUT_FILENAME: str  = ""
    DEFAULT_FORMAT: str = "instant"

    # ── Subscription ───────────────────────────────────────────────────────
    SUB_DISCOUNT_PCT: float | None = None   # None → auto via product.js

    # ── Collection filter ──────────────────────────────────────────────────
    SKIP_HANDLE_RE: re.Pattern | None = None
    HANDLE_FILTER: str | None = None        # keep only handles containing this string

    # ── Keyword extension ──────────────────────────────────────────────────
    EXTRA_FORMAT_KW: dict     = {}
    EXTRA_INGREDIENT_KW: list = []
    EXTRA_SKIP_KW: list       = []
    EXTRA_HANDLES: list       = []

    # ── Volume / serving size ──────────────────────────────────────────────
    SERVING_SIZE_G: float | None = None  # g/serving; if set, volume_g = serving_count * SERVING_SIZE_G

    # ── Post-processing ────────────────────────────────────────────────────
    DEDUPLICATE: bool = False

    # ──────────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self.today    = date.today().isoformat()
        self.out_file = RAW_DIR / self.OUT_FILENAME

        self.log = logging.getLogger(self.BRAND or __name__)
        if not self.log.handlers:
            h = logging.FileHandler(RAW_DIR / "scrape_errors.log")
            h.setFormatter(logging.Formatter(f"%(asctime)s | {self.BRAND} | %(message)s"))
            self.log.addHandler(h)
            self.log.setLevel(logging.ERROR)

        self._format_kw: dict[str, list[str]] = {**_BASE_FORMAT_KW}
        for k, v in self.EXTRA_FORMAT_KW.items():
            self._format_kw.setdefault(k, [])
            self._format_kw[k] = list(dict.fromkeys(self._format_kw[k] + v))

        self._ingredient_kw = list(dict.fromkeys(_BASE_INGREDIENT_KW + self.EXTRA_INGREDIENT_KW))
        self._skip_kw       = list(dict.fromkeys(_BASE_SKIP_KW + self.EXTRA_SKIP_KW))

    # ── Session ────────────────────────────────────────────────────────────

    def make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": _UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    # ── Inference helpers ──────────────────────────────────────────────────

    def infer_format(self, title: str) -> str:
        # Title-only per memory: body_html causes false format matches in bundles/kits
        t = title.lower()
        for fmt, kws in self._format_kw.items():
            if any(kw in t for kw in kws):
                return fmt
        return self.DEFAULT_FORMAT

    def infer_ingredient(self, title: str, body: str = "") -> str | None:
        text = (title + " " + body).lower()
        for ing in self._ingredient_kw:
            if ing in text:
                return ing
        return None

    def is_skip(self, title: str) -> bool:
        low = title.lower()
        return any(kw in low for kw in self._skip_kw)

    def extract_serving_count(self, title: str, body: str = "") -> int | None:
        for text in [title, body]:
            for pat in [r"(\d+)\s*servings?", r"(\d+)\s*-\s*serving", r"(\d+)\s*count\b"]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = int(m.group(1))
                    if 1 <= val <= 500:
                        return val
        return None

    def extract_volume_g(self, title: str, body: str = "") -> float | None:
        """Hook: return total package weight in grams, or None. Override in subclasses."""
        return None

    # ── Data fetchers ──────────────────────────────────────────────────────

    def get_handles(self, session: requests.Session) -> list[str]:
        handles: list[str] = []
        page_num = 1
        while True:
            url = f"{self.BASE}/collections/{self.COLLECTION}/products.json?limit=250&page={page_num}"
            try:
                r = session.get(url, timeout=15)
                if r.status_code != 200:
                    self.log.error("collection page=%d status=%d", page_num, r.status_code)
                    break
                products = r.json().get("products", [])
                if not products:
                    break
                for p in products:
                    h = p.get("handle", "")
                    if not h:
                        continue
                    if self.SKIP_HANDLE_RE and self.SKIP_HANDLE_RE.search(h):
                        continue
                    if self.HANDLE_FILTER and self.HANDLE_FILTER not in h:
                        continue
                    handles.append(h)
                if len(products) < 250:
                    break
                page_num += 1
            except Exception as e:
                self.log.error("collection page=%d: %s", page_num, e)
                break

        for h in self.EXTRA_HANDLES:
            if h not in handles:
                handles.append(h)
        return list(dict.fromkeys(handles))

    def get_product(self, session: requests.Session, handle: str) -> dict | None:
        url = f"{self.BASE}/products/{handle}.json"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                self.log.error("product %s status=%d", handle, r.status_code)
                return None
            return r.json().get("product", {})
        except Exception as e:
            self.log.error("product %s: %s", handle, e)
            return None

    def get_sub_pct(self, session: requests.Session, handle: str,
                    single_price: float | None = None) -> float | None:
        """
        Returns subscription discount % or None if no subscription.
        Override in subclass for non-standard subscription widgets (e.g. per_delivery_price).
        """
        if self.SUB_DISCOUNT_PCT is not None:
            return self.SUB_DISCOUNT_PCT

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
            adj = plans[0].get("price_adjustments", [{}])[0]
            if adj.get("value_type") == "percentage":
                return float(adj["value"])
        except Exception as e:
            self.log.error("product.js %s: %s", handle, e)
        return None

    # ── Row assembly ───────────────────────────────────────────────────────

    def _make_row(self, *, title: str, fmt: str, ingredient: str | None,
                  serving_size_g: float | None, serving_count: int | None,
                  volume_g: float | None, price: float, discount_pct: float,
                  serving_price: float | None, url: str, purchase_type: str) -> dict:
        return {
            "brand":          self.BRAND,
            "product_name":   title,
            "format":         fmt,
            "serving_size_g": serving_size_g,
            "serving_count":  serving_count,
            "volume_g":       volume_g,
            "price_usd":      price,
            "discount_pct":   discount_pct,
            "serving_price":  serving_price,
            "key_ingredient": ingredient,
            "channel":        "own_site",
            "url":            url,
            "date_collected": self.today,
            "purchase_type":  purchase_type,
        }

    # ── Product processing (override for complex variant/sub logic) ────────

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        """
        Default: one row per variant (single purchase), plus one per variant if
        subscription exists. Suitable for products with a single standard variant.
        Override for multi-variant or custom subscription logic.
        """
        title    = product.get("title", "")
        body_raw = product.get("body_html") or ""
        body     = re.sub(r"<[^>]+>", " ", body_raw)

        if self.is_skip(title):
            print(f"    SKIP: {title}")
            return []

        variants = product.get("variants", [])
        if not variants:
            return []

        price = float(variants[0].get("price", 0) or 0)
        if price <= 0:
            return []

        fmt           = self.infer_format(title)
        ingredient    = self.infer_ingredient(title, body)
        serving_count = self.extract_serving_count(title, body)
        product_url   = f"{self.BASE}/products/{handle}"

        volume_g = self.extract_volume_g(title, body)
        serving_size_g = self.SERVING_SIZE_G
        if volume_g is None and serving_size_g and serving_count:
            volume_g = round(serving_count * serving_size_g, 1)

        sp = round(price / serving_count, 2) if serving_count else None

        rows = [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=price, discount_pct=0,
            serving_price=sp, url=product_url, purchase_type="single",
        )]

        sub_pct = self.get_sub_pct(session, handle, price)
        if sub_pct is not None:
            sub_price = round(price * (1 - sub_pct / 100), 2)
            sub_sp    = round(sub_price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=sub_price, discount_pct=sub_pct,
                serving_price=sub_sp, url=product_url, purchase_type="subscription",
            ))

        return rows

    # ── Post-processing ────────────────────────────────────────────────────

    def _dedup(self, rows: list[dict]) -> list[dict]:
        seen: set = set()
        out: list[dict] = []
        for row in rows:
            key = (row["serving_count"], row["price_usd"], row["purchase_type"])
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out

    def _p(self, s: str) -> None:
        print(s.encode("ascii", errors="replace").decode("ascii"))

    # ── Main entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        session = self.make_session()

        self._p(f"Fetching {self.BRAND} handles from /{self.COLLECTION}...")
        handles = self.get_handles(session)
        self._p(f"Found {len(handles)} handles")

        all_rows: list[dict] = []
        for i, handle in enumerate(handles, 1):
            self._p(f"[{i}/{len(handles)}] {handle}")
            product = self.get_product(session, handle)
            if not product:
                continue
            rows = self.build_rows(handle, product, session)
            all_rows.extend(rows)
            if rows:
                r0 = rows[0]
                self._p(f"    {r0['product_name'][:50]} | {len(rows)} row(s)")
            time.sleep(random.uniform(2, 5))

        if self.DEDUPLICATE:
            before = len(all_rows)
            all_rows = self._dedup(all_rows)
            self._p(f"Deduped: {before} -> {len(all_rows)} rows")

        with open(self.out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)

        self._p(f"\nDone. {len(all_rows)} rows -> {self.out_file}")
