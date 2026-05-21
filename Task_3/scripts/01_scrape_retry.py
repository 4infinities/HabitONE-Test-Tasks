#!/usr/bin/env python3
"""
01_scrape_retry.py — Retry scraper for brands that failed in 01_scrape.py.

Targets:
  - Om Mushrooms    : prices are JS-rendered; needs wait_for_selector
  - North Spore     : prices in JSON-LD, not CSS class
  - HabitONE        : only got 4/44 products; needs wait_for_selector per product page
  - Everyday Dose   : SPA — try networkidle + longer wait
  - Pella Nutrition : SPA — try networkidle + longer wait

Writes/overwrites CSVs in data/raw/ for these brands only.
Run after 01_scrape.py.
"""

import re
import csv
import json
import time
import random
import logging
import requests
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv(Path(__file__).parent.parent / ".env")

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
TODAY   = date.today().isoformat()

logging.basicConfig(
    filename=RAW_DIR / "scrape_errors.log",
    level=logging.ERROR,
    format="%(asctime)s | %(message)s",
)

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "key_ingredient",
    "channel", "url", "date_collected",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Brands to retry ────────────────────────────────────────────────────────────

RETRY_BRANDS = [
    {
        "brand": "HabitONE",
        "own_site": "https://habitone.co/collections/all",
        "ebay_query": "HabitONE mushroom coffee",
        "wait_for": '[class*="price"]',
        "wait_until": "domcontentloaded",
    },
    {
        "brand": "Om Mushrooms",
        "own_site": "https://ommushrooms.com/pages/shop",
        "ebay_query": "Om Mushrooms coffee powder capsule",
        "wait_for": '[class*="price"]',
        "wait_until": "domcontentloaded",
    },
    {
        "brand": "North Spore",
        "own_site": "https://northspore.com/shop",
        "ebay_query": "North Spore mushroom coffee ground",
        "wait_for": None,       # uses JSON-LD; no reliable CSS price selector
        "wait_until": "domcontentloaded",
    },
    {
        "brand": "Everyday Dose",
        "own_site": "https://everydaydose.com/collections/all",
        "ebay_query": "Everyday Dose mushroom coffee lions mane",
        "wait_for": None,
        "wait_until": "networkidle",   # SPA — need full render
    },
    {
        "brand": "Pella Nutrition",
        "own_site": "https://mypellanutrition.com/",
        "ebay_query": "Pella Nutrition 7-mushroom coffee",
        "wait_for": None,
        "wait_until": "networkidle",
    },
]

# ── Selector fallback chains (same as main scraper) ────────────────────────────

NAME_SELECTORS = [
    "h1.product__title", "h1.product-single__title", "h1.product_name",
    "h1[itemprop='name']", ".product__title h1", ".product-title h1", "h1",
]
PRICE_SELECTORS = [
    "[data-product-price]", ".price__regular .price-item--regular",
    ".product__price .price", ".price .price-item", "span.price--highlight",
    "[itemprop='price']", ".product-price", "span.price", "[class*='price']",
]
COMPARE_PRICE_SELECTORS = [
    "[data-compare-price]", ".price__compare .price-item",
    "s.price-item--regular", ".price--compare", "del .price", "s.price",
]
DESCRIPTION_SELECTORS = [
    ".product__description", ".product-single__description", "#product-description",
    ".product-description", ".product__info-container .rte",
    "[itemprop='description']", ".description",
]

FORMAT_KEYWORDS: dict[str, list[str]] = {
    "packet":  ["packet", "sachet", "single serve", "single-serve", "stick pack"],
    "capsule": ["capsule", "cap", "pill", "tablet", "softgel", "vegcap"],
    "rtd":     ["ready to drink", "ready-to-drink", "rtd", "can", "bottle"],
    "pods":    ["pod", "k-cup", "kcup", "nespresso", "keurig"],
    "creamer": ["creamer", "creamer blend", "add-in", "topper"],
    "ground":  ["ground coffee", "whole bean", "drip coffee"],
    "instant": ["instant", "powder", "powdered", "canister", "tub", "scoop", "mix"],
}
INGREDIENT_KEYWORDS = [
    "lion's mane", "lions mane", "chaga", "reishi", "cordyceps",
    "turkey tail", "shiitake", "maitake", "ashwagandha", "rhodiola",
    "l-theanine", "theanine", "tongkat ali", "collagen", "adaptogen",
]


def infer_format(name, desc):
    text = (name + " " + desc).lower()
    for fmt, kws in FORMAT_KEYWORDS.items():
        if any(k in text for k in kws):
            return fmt
    return "other"


def infer_ingredient(name, desc):
    text = (name + " " + desc).lower()
    for ing in INGREDIENT_KEYWORDS:
        if ing in text:
            return ing
    return None


def infer_serving_size(desc):
    for pat in [
        r"serving size[:\s]+(\d+\.?\d*)\s*g",
        r"(\d+\.?\d*)\s*g\s*per serving",
        r"(\d+\.?\d*)\s*g\s*/\s*serving",
    ]:
        m = re.search(pat, desc.lower())
        if m:
            return float(m.group(1))
    return None


def infer_serving_count(name, desc):
    for pat in [r"(\d+)\s*servings?", r"(\d+)\s*count", r"(\d+)\s*ct\b"]:
        m = re.search(pat, (name + " " + desc).lower())
        if m:
            v = int(m.group(1))
            if 1 <= v <= 500:
                return v
    return None


def parse_price(text):
    if not text:
        return None
    m = re.search(r"[\$£€]?\s*(\d[\d,]*\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def find_price(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            v = parse_price(el.get_text(strip=True))
            if v and v > 0:
                return v
    return None


def extract_jsonld_price(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0]
            price = offers.get("price") or offers.get("lowPrice")
            if price:
                return float(price)
        except (json.JSONDecodeError, ValueError, IndexError, AttributeError, TypeError):
            continue
    return None


def select_first(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return ""


def delay():
    time.sleep(random.uniform(2, 5))


def log_error(brand, url, exc):
    logging.error("%s | %s | %s", brand, url, exc)
    print(f"    ERROR: {exc}")


def save_csv(brand_name, rows):
    slug = re.sub(r"[^\w]+", "_", brand_name.lower()).strip("_")
    path = RAW_DIR / f"{slug}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {len(rows)} rows saved to data/raw/{path.name}")


# ── Playwright scraper with wait_for_selector + JSON-LD fallback ───────────────

def scrape_brand(brand_config: dict) -> list[dict]:
    brand      = brand_config["brand"]
    coll_url   = brand_config["own_site"]
    wait_for   = brand_config.get("wait_for")
    wait_until = brand_config.get("wait_until", "domcontentloaded")
    rows: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx  = browser.new_context(user_agent=UA, ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            page.goto(coll_url, wait_until=wait_until, timeout=40000)
            time.sleep(3)

            hrefs: list[str] = page.eval_on_selector_all(
                "a[href*='/products/']",
                "els => [...new Set(els.map(e => e.href.split('?')[0]))]",
            )
            links = [h for h in hrefs if "/products/" in h][:30]

            if not links:
                log_error(brand, coll_url, Exception("no product links found"))
            else:
                print(f"  Found {len(links)} product links")

            for url in links:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)

                    # Wait for the price element to appear if a selector is given
                    if wait_for:
                        try:
                            page.wait_for_selector(wait_for, timeout=6000)
                        except PlaywrightTimeout:
                            pass  # proceed anyway; JSON-LD may still have the price

                    time.sleep(1)
                    soup = BeautifulSoup(page.content(), "lxml")

                    name  = select_first(soup, NAME_SELECTORS)
                    desc  = select_first(soup, DESCRIPTION_SELECTORS)
                    price = find_price(soup, PRICE_SELECTORS)

                    # JSON-LD fallback (covers North Spore and similar)
                    if price is None:
                        price = extract_jsonld_price(soup)
                    if price is None:
                        continue

                    compare  = find_price(soup, COMPARE_PRICE_SELECTORS)
                    discount = 0.0
                    if compare and compare > price:
                        discount = round((1 - price / compare) * 100, 1)

                    ss = infer_serving_size(desc)
                    sc = infer_serving_count(name, desc)

                    rows.append({
                        "brand":          brand,
                        "product_name":   name or None,
                        "format":         infer_format(name, desc),
                        "serving_size_g": ss,
                        "serving_count":  sc,
                        "volume_g":       round(ss * sc, 1) if ss and sc else None,
                        "price_usd":      price,
                        "discount_pct":   discount,
                        "key_ingredient": infer_ingredient(name, desc),
                        "channel":        "own_site",
                        "url":            url,
                        "date_collected": TODAY,
                    })
                    delay()

                except PlaywrightTimeout:
                    log_error(brand, url, Exception("timeout on product page"))
                except Exception as e:
                    log_error(brand, url, e)

        except Exception as e:
            log_error(brand, coll_url, e)
        finally:
            browser.close()

    return rows


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Retry scrape date: {TODAY}\n")
    for brand_config in RETRY_BRANDS:
        brand = brand_config["brand"]
        print(f"\n=== {brand} ===")
        rows = scrape_brand(brand_config)
        print(f"  own_site: {len(rows)} products")
        save_csv(brand, rows)
    print(f"\nDone. Errors in data/raw/scrape_errors.log")


if __name__ == "__main__":
    main()
