#!/usr/bin/env python3
"""
Manual link checker script for cx02-sales-ai.
Validates all product URLs, policy source URLs, and knowledge base source references.
Not run in automated CI (manual run only).
"""

import json
import re
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

BASE_DIR = Path(__file__).resolve().parent.parent

def collect_urls():
    urls = set()

    # 1. products.json
    prod_path = BASE_DIR / "data" / "products.json"
    if prod_path.exists():
        with open(prod_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for prod in data.get("products", {}).values():
                if prod.get("url"):
                    urls.add(prod["url"])
                for attr in prod.get("attributes", {}).values():
                    if isinstance(attr, dict) and attr.get("source_url"):
                        urls.add(attr["source_url"])

    # 2. policies.json
    pol_path = BASE_DIR / "data" / "policies.json"
    if pol_path.exists():
        with open(pol_path, "r", encoding="utf-8") as f:
            policies = json.load(f)
            for val in policies.values():
                if isinstance(val, dict):
                    if val.get("source_url"):
                        urls.add(val["source_url"])
                    if val.get("track_url"):
                        urls.add(val["track_url"])

    # 3. data/kb/*.md
    for kb_file in (BASE_DIR / "data" / "kb").glob("*.md"):
        content = kb_file.read_text(encoding="utf-8")
        found = re.findall(r'https?://[^\s\)\"\'>]+', content)
        for u in found:
            urls.add(u)

    return sorted(list(urls))


def check_url(url: str, timeout: int = 15):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KeplerTechLinkChecker/1.0)"}
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - t0
            return resp.status, elapsed, None
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        return e.code, elapsed, str(e)
    except Exception as e:
        elapsed = time.time() - t0
        return 0, elapsed, str(e)


def main():
    urls = collect_urls()
    print(f"Checking {len(urls)} distinct links across products, policies, and knowledge base...\n")

    all_passed = True
    for i, url in enumerate(urls, 1):
        status, elapsed, err = check_url(url)
        status_str = f"[{status}]" if status else "[FAILED]"
        time_str = f"{elapsed:.2f}s"
        if 200 <= status < 400:
            print(f"{i:2d}. OK   {status_str:8s} {time_str:7s} -> {url}")
        else:
            print(f"{i:2d}. FAIL {status_str:8s} {time_str:7s} -> {url} (Error: {err})")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("Link check PASSED: All URLs are live and reachable.")
        return 0
    else:
        print("Link check FAILED: Some URLs are unreachable.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
