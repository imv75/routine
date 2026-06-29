#!/usr/bin/env python3
"""Test Playwright with Acalog catalog - discover structure and AJAX endpoints."""

import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

CHROMIUM_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

def test_acalog(name, url):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print('='*60)

    ajax_responses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROMIUM_PATH,
            proxy={"server": "http://127.0.0.1:33943"},
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120",
        )

        # Intercept responses to find AJAX endpoints
        def on_response(response):
            url_resp = response.url
            status = response.status
            ct = response.headers.get("content-type", "")
            if "catalog" in url_resp and status == 200 and len(response.body()) > 100:
                ajax_responses.append({
                    "url": url_resp,
                    "status": status,
                    "content_type": ct,
                    "size": len(response.body()),
                })

        page = context.new_page()
        page.on("response", on_response)
        page.set_default_timeout(45000)

        print("Loading page...")
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"Timeout/error on goto: {e}")
            try:
                page.wait_for_selector("body", timeout=10000)
            except:
                pass

        time.sleep(3)

        content = page.content()
        print(f"Rendered page size: {len(content):,} bytes")

        soup = BeautifulSoup(content, "html.parser")

        # Check for course blocks
        blocks = soup.find_all("div", class_="courseblock")
        print(f"div.courseblock elements: {len(blocks)}")

        if blocks:
            # Show first block
            b = blocks[0]
            print("First courseblock:")
            print(b.get_text()[:300])

        # Check for subject links
        subj_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "navoid=" in href or "subject=" in href or "coid=" in href:
                subj_links.append((a.get_text(strip=True)[:40], href[:80]))

        print(f"\nSubject/dept links: {len(subj_links)}")
        for text, href in subj_links[:10]:
            print(f"  {text} -> {href}")

        # Check for pagination
        pages_info = soup.find_all(["span", "a"], class_=lambda c: c and "page" in c.lower())
        print(f"\nPagination elements: {len(pages_info)}")

        # Look at overall structure
        print("\nPage text preview (1000 chars):")
        print(soup.get_text()[:1000])

        # Show AJAX responses
        print(f"\nAJAX responses intercepted: {len(ajax_responses)}")
        for resp in ajax_responses[:10]:
            print(f"  {resp['status']} {resp['size']:,}b {resp['content_type'][:40]}: {resp['url'][:100]}")

        browser.close()

    return len(blocks) > 0, subj_links


if __name__ == "__main__":
    # Test LSU
    has_blocks, links = test_acalog(
        "Louisiana State University",
        "https://catalog.lsu.edu/content.php?catoid=26&navoid=2296"
    )
    print(f"\nResult: has_blocks={has_blocks}, dept_links={len(links)}")
