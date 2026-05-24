#!/usr/bin/env python3
"""
playwright_base.py — Base class for Playwright-driven brand scrapers.

Subclass must implement:
    scrape_product(page, handle: str, rows: list[dict]) -> None

Override get_handles_playwright(page) if the default regex approach doesn't work
(e.g. paginated collection, JSON-first with Playwright fallback).
"""

import re
import csv
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shopify_scraper_template import ShopifyScraperBase, CSV_FIELDS, _UA

from playwright.sync_api import sync_playwright


class PlaywrightScraperBase(ShopifyScraperBase):

    def get_handles_playwright(self, page) -> list[str]:
        """Default: extract handles via regex from collection HTML."""
        col_url = f"{self.BASE}/collections/{self.COLLECTION}"
        page.goto(col_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        html = page.content()
        handles = re.findall(r"/products/([a-z0-9][a-z0-9\-]+)", html)
        handles = list(dict.fromkeys(handles))
        if self.SKIP_HANDLE_RE:
            handles = [h for h in handles if not self.SKIP_HANDLE_RE.search(h)]
        for h in self.EXTRA_HANDLES:
            if h not in handles:
                handles.append(h)
        return handles

    def scrape_product(self, page, handle: str, rows: list[dict]) -> None:
        raise NotImplementedError

    def run(self) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_UA, locale="en-US")
            page = ctx.new_page()
            page.goto(f"{self.BASE}/?currency=USD", wait_until="domcontentloaded")
            time.sleep(1)

            handles = self.get_handles_playwright(page)
            self._p(f"Found {len(handles)} handles")

            rows: list[dict] = []
            for i, handle in enumerate(handles, 1):
                self._p(f"[{i}/{len(handles)}] {handle}")
                self.scrape_product(page, handle, rows)
                time.sleep(random.uniform(2, 4))

            browser.close()

        with open(self.out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        self._p(f"\nDone. {len(rows)} rows -> {self.out_file}")
