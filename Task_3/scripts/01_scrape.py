#!/usr/bin/env python3
"""
01_scrape.py — Unified scraper for HabitONE competitive analysis.

Scrapes 17 brands from own sites (BS4 + Playwright fallback) and eBay
search results (BS4 — ebay.com/sch renders in static HTML).
Amazon is manual-only — provide data/raw/amazon_manual.csv separately.

Outputs one CSV per brand in data/raw/.
Errors logged to data/raw/scrape_errors.log.
"""

import re
import csv
import time
import random
import logging
import requests
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus
from dotenv import load_dotenv
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. JS-rendered sites will fall back to BS4 only.")

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
TODAY = date.today().strftime("%d.%m.%Y")

logging.basicConfig(
    filename=RAW_DIR / "scrape_errors.log",
    level=logging.ERROR,
    format="%(asctime)s | %(message)s",
)

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "key_ingredient",
    "channel", "url", "date_collected", "purchase_type", "add_ons",
]

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"

# ── Brand config ───────────────────────────────────────────────────────────────
# method: "bs4" tries BeautifulSoup first; "playwright" goes straight to Playwright.
# BS4 auto-falls back to Playwright when no rows are found.

# HabitONE and Four Sigmatic are replaced by hand-collected CSVs (habitone_manual.csv,
# four_sigmatic_manual.csv) — do NOT re-scrape them here.

BRANDS = [
    {
        "brand": "Ryze",
        "own_site": "https://ryzesuperfoods.com/collections/all",
        "method": "bs4",          # static HTML confirmed
        "ebay_query": "Ryze mushroom coffee superfoods",
    },
    {
        "brand": "MudWtr",
        "own_site": "https://mudwtr.com/collections/shop",
        "method": "playwright",   # 403 on requests
        "ebay_query": "MudWtr mushroom coffee alternative",
    },
    {
        "brand": "Everyday Dose",
        "own_site": "https://everydaydose.com/collections/all",
        "method": "shopify_json",  # product pages return 403; prices are in variants JSON
        "ebay_query": "Everyday Dose mushroom coffee lions mane",
    },
    {
        "brand": "Shroomi",
        "own_site": "https://www.shroomihealth.com/collections/functional-mushroom-coffee",
        "method": "playwright",
        "ebay_query": "Shroomi mushroom coffee organic",
    },
    {
        "brand": "Rasa",
        "own_site": "https://wearerasa.com/collections/all-products",  # rasacoffee.com is for sale
        "method": "playwright",
        "ebay_query": "Rasa adaptogen coffee mushroom",
    },
    {
        "brand": "Om Mushrooms",
        "own_site": "https://ommushrooms.com/pages/shop",  # /pages/shop has 80 product links; prices are JS-rendered
        "method": "playwright",
        "ebay_query": "Om Mushrooms coffee powder capsule",
    },
    {
        "brand": "BodyBrain Coffee",
        "own_site": "https://bodybraincoffee.com/collections/all",
        "method": "bs4",
        "ebay_query": "BodyBrain mushroom coffee tongkat ali",
    },
    {
        "brand": "IQJOE",
        "own_site": "https://eatiqbar.com/collections/iqjoe",
        "method": "bs4",
        "ebay_query": "IQJOE mushroom coffee nootropic",
    },
    {
        "brand": "Clevr Blends",
        "own_site": "https://clevrblends.com/collections/all",
        "method": "bs4",          # static HTML confirmed; 152 product links
        "ebay_query": "Clevr Blends adaptogen latte",
    },
    {
        "brand": "Strong Coffee Co.",
        "own_site": "https://strongcoffeecompany.com/collections/all",
        "method": "bs4",
        "ebay_query": "Strong Coffee Company adaptogen instant",
    },
    {
        "brand": "La Republica",
        "own_site": "http://larepublicacoffee.com/collections/all",  # https has broken TLS on their server
        "method": "bs4",
        "ebay_query": "La Republica mushroom coffee organic",
    },
    {
        "brand": "Renude",
        "own_site": "https://drinkrenude.com/collections/all",
        "method": "bs4",
        "ebay_query": "Renude Chagaccino mushroom coffee",
    },
    {
        "brand": "North Spore",
        "own_site": "https://northspore.com/collections/mushroom-drinks",  # only collection with coffee SKUs
        "method": "shopify_json",
        "ebay_query": "North Spore mushroom coffee ground",
    },
    {
        "brand": "Nootrum",
        "own_site": "https://nootrum.com/collections/all",
        "method": "bs4",
        "ebay_query": "Nootrum mushroom coffee powder",
    },
    {
        "brand": "Pella Nutrition",
        "own_site": None,          # WordPress site, no product pages; sold via Amazon only
        "method": "skip",
        "ebay_query": "Pella Nutrition 7-mushroom coffee",
    },
]

# ── CSS selector fallback chains ───────────────────────────────────────────────
# Tried in order; first selector that returns a non-empty result wins.
# These cover common Shopify + custom storefront patterns.

PRODUCT_LINK_SELECTORS = [
    "a[href*='/products/']",
    ".product-card a",
    ".product-item a",
    ".grid__item a",
    ".boost-pfs-filter-product-item-inner a",
    "li.product a",
]

NAME_SELECTORS = [
    "h1.product__title",
    "h1.product-single__title",
    "h1.product_name",
    "h1[itemprop='name']",
    ".product__title h1",
    ".product-title h1",
    "h1",
]

PRICE_SELECTORS = [
    "[data-product-price]",
    ".price__regular .price-item--regular",
    ".product__price .price",
    ".price .price-item",
    "span.price--highlight",
    "[itemprop='price']",
    ".product-price",
    "span.price",
    "[class*='price']",   # broad fallback for custom Shopify themes
]

COMPARE_PRICE_SELECTORS = [
    "[data-compare-price]",
    ".price__compare .price-item",
    "s.price-item--regular",
    ".price--compare",
    "del .price",
    "s.price",
]

DESCRIPTION_SELECTORS = [
    ".product__description",
    ".product-single__description",
    "#product-description",
    ".product-description",
    ".product__info-container .rte",
    "[itemprop='description']",
    ".description",
]

# ── Metadata inference ─────────────────────────────────────────────────────────

FORMAT_KEYWORDS: dict[str, list[str]] = {
    "packet":  ["packet", "sachet", "single serve", "single-serve", "stick pack", "on-the-go"],
    "capsule": ["capsule", "cap", "pill", "tablet", "softgel", "vegcap"],
    "rtd":     ["ready to drink", "ready-to-drink", "rtd", "canned", "12oz can", "16oz can"],
    "pods":    ["pod", "k-cup", "kcup", "nespresso", "keurig"],
    "creamer": ["creamer", "creamer blend", "add-in", "topper"],
    "ground":  ["ground coffee", "whole bean", "drip coffee", "filter coffee"],
    "instant": ["instant", "powder", "powdered", "canister", "tub", "scoop", "mix"],
}

INGREDIENT_KEYWORDS = [
    "lion's mane", "lions mane",
    "chaga",
    "reishi",
    "cordyceps",
    "turkey tail",
    "shiitake",
    "maitake",
    "ashwagandha",
    "rhodiola",
    "l-theanine", "theanine",
    "tongkat ali",
    "collagen",
    "adaptogen",
]


def infer_format(name: str, description: str) -> str:
    text = (name + " " + description).lower()
    for fmt, keywords in FORMAT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return fmt
    return "other"


def infer_ingredient(name: str, description: str) -> str | None:
    text = (name + " " + description).lower()
    for ing in INGREDIENT_KEYWORDS:
        if ing in text:
            return ing
    return None


def infer_serving_size(description: str) -> float | None:
    text = description.lower()
    for pat in [
        r"serving size[:\s]+(\d+\.?\d*)\s*g",
        r"(\d+\.?\d*)\s*g\s*per serving",
        r"(\d+\.?\d*)\s*g\s*/\s*serving",
        r"per serving[:\s]+(\d+\.?\d*)\s*g",
    ]:
        m = re.search(pat, text)
        if m:
            return float(m.group(1))
    return None


def infer_serving_count(name: str, description: str) -> int | None:
    text = (name + " " + description).lower()
    for pat in [
        r"(\d+)\s*servings?",
        r"(\d+)\s*count",
        r"(\d+)\s*ct\b",
        r"(\d+)\s*srv\b",
    ]:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:
                return val
    return None


def parse_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.strip().replace(",", "")
    m = re.search(r"[\$£€]?\s*(\d[\d]*\.?\d*)", cleaned)
    if not m:
        return None
    val = float(m.group(1))
    # Shopify stores prices as integer cents in data attributes (e.g. 2980 = $29.80).
    # If the value is a whole number > 500, divide by 100.
    if val > 500 and val == int(val):
        val = round(val / 100, 2)
    return val if val > 0 else None


# ── Utilities ──────────────────────────────────────────────────────────────────

def delay():
    time.sleep(random.uniform(2, 5))


def log_error(brand: str, url: str, exc: Exception):
    logging.error("%s | %s | %s", brand, url, exc)
    print(f"    ERROR: {exc}")


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def select_first(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return ""


def base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _shopify_json_endpoint(collection_url: str) -> tuple[str, str]:
    """Return (base_url, products_json_prefix) for a given Shopify collection or root URL."""
    p = urlparse(collection_url)
    b = f"{p.scheme}://{p.netloc}"
    path = p.path.rstrip("/")
    if "/collections/" in path:
        return b, f"{b}{path}/products.json"
    return b, f"{b}/products.json"


def product_links_shopify_json(collection_url: str) -> list[str]:
    """Fetch all product handles via Shopify's products.json API (no HTML parsing needed)."""
    b, endpoint = _shopify_json_endpoint(collection_url)
    links: list[str] = []
    page = 1
    while True:
        try:
            resp = SESSION.get(f"{endpoint}?limit=250&page={page}", timeout=15)
            if resp.status_code != 200:
                break
            products = resp.json().get("products", [])
            if not products:
                break
            for p in products:
                handle = p.get("handle")
                if handle:
                    links.append(f"{b}/products/{handle}")
            if len(products) < 250:
                break
            page += 1
            time.sleep(0.5)
        except Exception:
            break
    return links


def rows_from_shopify_json(brand: str, collection_url: str) -> list[dict]:
    """Build rows directly from Shopify products JSON — prices come from variant data,
    no product-page visit needed. Used for brands that block direct page requests."""
    b, endpoint = _shopify_json_endpoint(collection_url)
    rows: list[dict] = []
    page = 1
    while True:
        try:
            resp = SESSION.get(f"{endpoint}?limit=250&page={page}", timeout=15)
            if resp.status_code != 200:
                break
            products = resp.json().get("products", [])
            if not products:
                break
            for p in products:
                title = p.get("title", "")
                body = BeautifulSoup(p.get("body_html", ""), "lxml").get_text(" ")
                tags = " ".join(p.get("tags", []))
                text_all = f"{title} {tags} {body}"
                product_url = f"{b}/products/{p['handle']}"
                for v in p.get("variants", []):
                    price = float(v.get("price") or 0)
                    if price <= 0:
                        continue
                    compare = float(v.get("compare_at_price") or 0)
                    discount = 0.0
                    if compare and compare > price:
                        discount = round((1 - price / compare) * 100, 1)
                    var_title = v.get("title", "Default Title")
                    name = f"{title} ({var_title})" if var_title != "Default Title" else title
                    sc_text = f"{var_title} {title}"
                    serving_count = infer_serving_count(sc_text, body)
                    serving_size = infer_serving_size(body)
                    if serving_size and serving_count:
                        volume: float | None = round(serving_size * serving_count, 1)
                    else:
                        w = float(v.get("weight") or 0)
                        wunit = v.get("weight_unit", "g")
                        if w > 0:
                            if wunit == "lb":
                                volume = round(w * 453.592, 1)
                            elif wunit == "oz":
                                volume = round(w * 28.3495, 1)
                            elif wunit == "kg":
                                volume = round(w * 1000, 1)
                            else:
                                volume = w
                        else:
                            volume = infer_volume_g(title, body)
                    rows.append({
                        "brand": brand,
                        "product_name": name,
                        "format": infer_format(title, text_all),
                        "serving_size_g": serving_size,
                        "serving_count": serving_count,
                        "volume_g": volume,
                        "price_usd": price,
                        "discount_pct": discount,
                        "key_ingredient": infer_ingredient(title, text_all),
                        "channel": "own_site",
                        "url": product_url,
                        "date_collected": TODAY,
                        "purchase_type": "single",
                        "add_ons": "",
                    })
            if len(products) < 250:
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            log_error(brand, endpoint, e)
            break
    return rows


def product_links_all_html(collection_url: str) -> list[str]:
    """Scrape all product links from HTML collection pages, following Shopify ?page= pagination."""
    seen: set[str] = set()
    links: list[str] = []
    page_num = 1
    while True:
        url = collection_url if page_num == 1 else f"{collection_url}?page={page_num}"
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            break
        new_links: list[str] = []
        for sel in PRODUCT_LINK_SELECTORS:
            for a in soup.select(sel):
                href = a.get("href", "")
                if not href or href == "#":
                    continue
                full = urljoin(base_url(collection_url), href).split("?")[0]
                if "/products/" in full and full not in seen:
                    seen.add(full)
                    new_links.append(full)
            if new_links:
                break
        if not new_links:
            break
        links.extend(new_links)
        has_next = (
            soup.select_one("a[rel='next']") or
            soup.select_one(".pagination__next") or
            soup.select_one("a.next") or
            soup.select_one("a[href*='page=']")
        )
        if not has_next:
            break
        page_num += 1
        time.sleep(0.5)
    return links


def find_price(soup: BeautifulSoup, selectors: list[str]) -> float | None:
    """Try each selector in order; return the first that yields a parseable price > 0."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            val = parse_price(el.get_text(strip=True))
            if val and val > 0:
                return val
    return None


def infer_volume_g(name: str, description: str) -> float | None:
    text = (name + " " + description).lower()
    # oz wins over g since US products label in oz
    m = re.search(r"(\d+\.?\d*)\s*oz\b", text)
    if m:
        return round(float(m.group(1)) * 28.3495, 1)
    m = re.search(r"(\d+\.?\d*)\s*lbs?\b", text)
    if m:
        return round(float(m.group(1)) * 453.592, 1)
    m = re.search(r"(\d+\.?\d*)\s*g\b", text)
    if m:
        val = float(m.group(1))
        if 10 <= val <= 5000:
            return val
    return None


def row_from_soup(soup: BeautifulSoup, brand: str, url: str, channel: str) -> dict | None:
    name = " ".join(select_first(soup, NAME_SELECTORS).split())
    desc = " ".join(select_first(soup, DESCRIPTION_SELECTORS).split())

    price = find_price(soup, PRICE_SELECTORS)
    if price is None:
        return None

    compare = find_price(soup, COMPARE_PRICE_SELECTORS)
    discount = 0.0
    if compare and compare > price:
        discount = round((1 - price / compare) * 100, 1)

    serving_size = infer_serving_size(desc)
    serving_count = infer_serving_count(name, desc)
    if serving_size and serving_count:
        volume = round(serving_size * serving_count, 1)
    else:
        volume = infer_volume_g(name, desc)

    return {
        "brand": brand,
        "product_name": name or None,
        "format": infer_format(name, desc),
        "serving_size_g": serving_size,
        "serving_count": serving_count,
        "volume_g": volume,
        "price_usd": price,
        "discount_pct": discount,
        "key_ingredient": infer_ingredient(name, desc),
        "channel": channel,
        "url": url,
        "date_collected": TODAY,
        "purchase_type": "single",
        "add_ons": "",
    }


# ── BS4 scraper ────────────────────────────────────────────────────────────────

def scrape_own_site_bs4(brand_config: dict) -> list[dict]:
    brand = brand_config["brand"]
    collection_url = brand_config["own_site"]
    rows: list[dict] = []

    links = product_links_shopify_json(collection_url)
    if links:
        print(f"  JSON API: {len(links)} products")
    else:
        links = product_links_all_html(collection_url)
        print(f"  HTML scrape: {len(links)} products")

    if not links:
        log_error(brand, collection_url, Exception("no product links found"))
        return rows

    for url in links:
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
            product_soup = BeautifulSoup(resp.text, "lxml")
            row = row_from_soup(product_soup, brand, url, "own_site")
            if row:
                rows.append(row)
        except Exception as e:
            log_error(brand, url, e)
        delay()

    return rows


# ── Subscription price detection ──────────────────────────────────────────────
# Tries to click a "subscribe & save" option and read the new price.
# Returns a subscription row dict, or None if not found / price unchanged.

_SUBSCRIBE_CLICK_SELECTORS = [
    "input[value='subscription']",
    "input[id*='subscribe']",
    "input[name='selling_plan']",
    "[data-selling-plan-id]",
    "label:has-text('Subscribe & Save')",
    "label:has-text('Subscribe')",
    ".rc-option--subscribe",
    "[class*='subscription-option']",
]

_SAVE_BADGE_SELECTORS = [
    ".rc-option__save", ".subscription-badge", "[class*='save-badge']",
    "[class*='subscription-discount']", "[class*='discount-badge']",
]


def _try_subscription_row(page, base_row: dict) -> dict | None:
    for sel in _SUBSCRIBE_CLICK_SELECTORS:
        try:
            el = page.query_selector(sel)
            if not el:
                continue
            el.click()
            page.wait_for_timeout(700)
            sub_soup = BeautifulSoup(page.content(), "lxml")
            sub_price = find_price(sub_soup, PRICE_SELECTORS)
            if sub_price and sub_price < base_row["price_usd"]:
                sub_row = dict(base_row)
                sub_row["price_usd"] = sub_price
                sub_row["purchase_type"] = "subscription"
                # Try to get displayed "save X%" badge
                for disc_sel in _SAVE_BADGE_SELECTORS:
                    el_d = sub_soup.select_one(disc_sel)
                    if el_d:
                        m = re.search(r"(\d+)\s*%", el_d.get_text())
                        if m:
                            sub_row["discount_pct"] = int(m.group(1))
                            break
                return sub_row
        except Exception:
            continue
    return None


# ── Playwright scraper ─────────────────────────────────────────────────────────

def _playwright_product_links(page, collection_url: str) -> list[str]:
    """Walk Shopify ?page= pagination in a live Playwright page."""
    seen: set[str] = set()
    links: list[str] = []
    page_num = 1
    while True:
        url = collection_url if page_num == 1 else f"{collection_url}?page={page_num}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        hrefs: list[str] = page.eval_on_selector_all(
            "a[href*='/products/']",
            "els => [...new Set(els.map(e => e.href.split('?')[0]))]",
        )
        new_links = [h for h in hrefs if "/products/" in h and h not in seen]
        if not new_links:
            break
        seen.update(new_links)
        links.extend(new_links)
        has_next = page.query_selector("a[rel='next'], .pagination__next, a.next")
        if not has_next:
            break
        page_num += 1
        time.sleep(0.5)
    return links


def scrape_own_site_playwright(brand_config: dict) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        log_error(brand_config["brand"], brand_config["own_site"], Exception("playwright not available"))
        return []

    brand = brand_config["brand"]
    collection_url = brand_config["own_site"]
    rows: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=HEADERS["User-Agent"], ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            # Try Shopify JSON API first (complete, no browser needed)
            links = product_links_shopify_json(collection_url)
            if links:
                print(f"  JSON API: {len(links)} products")
            else:
                links = _playwright_product_links(page, collection_url)
                print(f"  Playwright HTML: {len(links)} products")

            if not links:
                log_error(brand, collection_url, Exception("no product links found (playwright)"))

            for url in links:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(1)
                    soup = BeautifulSoup(page.content(), "lxml")
                    row = row_from_soup(soup, brand, url, "own_site")
                    if row:
                        sub_row = _try_subscription_row(page, row)
                        if sub_row:
                            rows.append(sub_row)
                        rows.append(row)
                    delay()
                except PlaywrightTimeout:
                    log_error(brand, url, Exception("playwright timeout"))
                except Exception as e:
                    log_error(brand, url, e)
        except Exception as e:
            log_error(brand, collection_url, e)
        finally:
            browser.close()

    return rows


def scrape_own_site(brand_config: dict) -> list[dict]:
    brand = brand_config["brand"]
    method = brand_config.get("method", "bs4")
    own_site = brand_config.get("own_site")

    if method == "skip" or own_site is None:
        print(f"  Skipping {brand} (no scrapeable own-site — manual collection required)")
        return []

    print(f"  own_site [{method}]: {own_site}")

    if method == "shopify_json":
        rows = rows_from_shopify_json(brand, own_site)
        print(f"  shopify_json: {len(rows)} rows extracted")
        return rows

    if method == "playwright":
        return scrape_own_site_playwright(brand_config)

    rows = scrape_own_site_bs4(brand_config)
    if not rows and PLAYWRIGHT_AVAILABLE:
        print(f"  BS4 returned 0 rows — falling back to Playwright")
        rows = scrape_own_site_playwright(brand_config)
    return rows


# ── eBay scraper (Playwright, single session) ──────────────────────────────────
# eBay blocks plain requests; Playwright with a real browser fingerprint bypasses it.
# All brands are scraped in one browser session to avoid repeated launch overhead.

def _parse_ebay_soup(soup: BeautifulSoup, brand: str) -> list[dict]:
    rows: list[dict] = []
    for item in soup.select(".s-item"):
        title_el = item.select_one(".s-item__title")
        price_el = item.select_one(".s-item__price")
        link_el  = item.select_one(".s-item__link")
        if not title_el or not price_el or not link_el:
            continue
        name = title_el.get_text(strip=True)
        if name.lower() == "shop on ebay":
            continue
        price = parse_price(price_el.get_text(strip=True))
        if price is None:
            continue
        rows.append({
            "brand": brand,
            "product_name": " ".join(name.split()),
            "format": infer_format(name, ""),
            "serving_size_g": None,
            "serving_count": None,
            "volume_g": None,
            "price_usd": price,
            "discount_pct": 0,
            "key_ingredient": infer_ingredient(name, ""),
            "channel": "ebay",
            "url": link_el.get("href", "").split("?")[0],
            "date_collected": TODAY,
            "purchase_type": "single",
            "add_ons": "",
        })
    return rows


def scrape_all_ebay(brands: list[dict]) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {b["brand"]: [] for b in brands}
    if not PLAYWRIGHT_AVAILABLE:
        print("Warning: Playwright not available — skipping eBay")
        return results

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=HEADERS["User-Agent"], ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for brand_config in brands:
            brand = brand_config["brand"]
            query = brand_config["ebay_query"]
            url = f"{EBAY_SEARCH_URL}?_nkw={quote_plus(query)}&_sacat=0&LH_BIN=1"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)  # eBay needs a bit more time to render results
                rows = _parse_ebay_soup(BeautifulSoup(page.content(), "lxml"), brand)
                results[brand] = rows
                print(f"  eBay {brand}: {len(rows)} listings")
            except Exception as e:
                log_error(brand, url, e)
                print(f"  eBay {brand}: 0 listings (error)")
            delay()

        browser.close()
    return results


# ── CSV output ─────────────────────────────────────────────────────────────────

def save_csv(brand_name: str, rows: list[dict]):
    slug = re.sub(r"[^\w]+", "_", brand_name.lower()).strip("_")
    path = RAW_DIR / f"{slug}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {len(rows)} rows saved to data/raw/{path.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Scrape date: {TODAY}\n")

    # Collect own-site rows per brand first
    own_rows_by_brand: dict[str, list[dict]] = {}
    for brand_config in BRANDS:
        brand = brand_config["brand"]
        print(f"\n=== {brand} ===")
        rows = scrape_own_site(brand_config)
        own_rows_by_brand[brand] = rows
        print(f"  own_site: {len(rows)} products")

    # Scrape eBay for all brands in a single Playwright session
    print("\n--- eBay pass ---")
    ebay_rows_by_brand = scrape_all_ebay(BRANDS)

    # Write one CSV per brand
    print("\n--- Writing CSVs ---")
    for brand_config in BRANDS:
        brand = brand_config["brand"]
        save_csv(brand, own_rows_by_brand[brand] + ebay_rows_by_brand[brand])

    print(f"\nDone. Errors logged to data/raw/scrape_errors.log")


if __name__ == "__main__":
    main()
