#!/usr/bin/env python3
"""
Debug: fetch B0D1J7XPJK and dump price-related HTML fragments.
Delete after fix is confirmed.
"""

import re
import warnings
warnings.filterwarnings("ignore")

try:
    from langchain_ollama import ChatOllama as _ChatOllama
    import langchain_community.chat_models as _lcm
    if not hasattr(_lcm, "ChatOllama"):
        _lcm.ChatOllama = _ChatOllama
except ImportError:
    pass

from bs4 import BeautifulSoup
from scrapegraphai.docloaders import ChromiumLoader

URL = "https://www.amazon.com/dp/B0D1J7XPJK"

print(f"Fetching {URL} ...")
loader = ChromiumLoader([URL], headless=True, load_state="load", timeout=60)
docs = loader.load()
html = docs[0].page_content if docs else ""
print(f"HTML length: {len(html)} chars\n")

if not html:
    print("Empty HTML — bot block or fetch error.")
    exit()

soup = BeautifulSoup(html, "lxml")

# 1. Title
title_el = soup.select_one("#productTitle")
print(f"[title] {title_el.get_text(strip=True)[:120] if title_el else 'NOT FOUND'}\n")

# 2. All .a-price .a-offscreen
print("[.a-price .a-offscreen]")
for el in soup.select(".a-price .a-offscreen"):
    parent_classes = el.find_parent(class_="a-price").get("class", []) if el.find_parent(class_="a-price") else []
    print(f"  '{el.get_text(strip=True)}'  parent-classes: {parent_classes}")

# 3. basisPrice
print("\n[basisPrice .a-offscreen]")
for el in soup.select(".basisPrice .a-offscreen"):
    print(f"  '{el.get_text(strip=True)}'")

# 4. SNS / subscribe
print("\n[[id*=sns] .a-offscreen  +  .snsPriceLabelValue]")
for el in soup.select('[id*="sns"] .a-offscreen, .snsPriceLabelValue'):
    print(f"  '{el.get_text(strip=True)}'")

# 5. savingsPercentage
print("\n[.savingsPercentage]")
for el in soup.select(".savingsPercentage"):
    print(f"  '{el.get_text(strip=True)}'")

# 6. Fallback — any raw $X.XX in core price block
print("\n[raw price regex in first 8000 chars of HTML]")
for m in re.findall(r"\$\d+\.\d+", html[:8000]):
    print(f"  {m}", end="  ")
print()

# 7. Check for CAPTCHA / bot block
if "captcha" in html.lower() or "Enter the characters" in html:
    print("\n*** CAPTCHA detected — Amazon blocked the request ***")
