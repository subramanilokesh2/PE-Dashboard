"""Browser smoke test: loads every module, opens one drawer per module, records console errors.
Requires: pip install playwright && python -m playwright install chromium  (optional; not needed to run the app)
Usage: python tests/browser_smoke.py http://127.0.0.1:5055
"""
import sys
from playwright.sync_api import sync_playwright

ROUTES = ["overview", "accounts", "portfolio", "signals", "industry", "stakeholders", "opportunities", "outreach"]

def main(base):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=None)
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        page.on("console", lambda m: errors.append(f"console:{m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.goto(base + "/#/overview", wait_until="networkidle")
        for r in ROUTES:
            page.goto(f"{base}/#/{r}", wait_until="networkidle")
            page.wait_for_selector("#view h1.page-title", timeout=15000)
            page.wait_for_function("() => !document.querySelector('#view tbody .skeleton') && !document.querySelector('#view .skeleton')", timeout=20000)
            title = page.inner_text("#view h1.page-title")
            rows = page.locator("#view tbody tr[data-id]").count()
            print(f"{r:14s} title={title!r} table_rows_on_page={rows}")
            if rows and rows < 40:
                first = page.locator("#view tbody tr[data-id]").first
                if first.count():
                    first.click()
                    page.wait_for_selector("#drawer.open", timeout=8000)
                    print(f"               drawer opened: {page.inner_text('#drawerBody h2')[:60]!r}")
                    page.keyboard.press("Escape")
            page.screenshot(path=f"/home/claude/work/shots/{r}.png", full_page=False)
        browser.close()
    print("console/page errors:", len(errors))
    for e in errors[:20]: print("  ", e)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5055")
