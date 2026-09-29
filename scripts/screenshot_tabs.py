"""Dev-only: screenshot every tab in light and dark themes, empty and loaded, plus the
Out-of-scope verdict, into docs/screenshots/experiment-tabs/ (blueprint §15, Phase 16).

Needs Playwright (pip install playwright && playwright install chromium); not a runtime
dependency. Usage: python scripts/screenshot_tabs.py
It starts the app (and scripts/screenshot_harness.py) with no API key, so nothing it
does can call Gemini: the loaded states use recorded quick-picks and demo datasets.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "experiment-tabs"
APP_PORT, HARNESS_PORT = 8771, 8772
WIDTH = 1440
TABS = ["1 · System Audit", "2 · Dataset Bias", "3 · Synthetic Media", "4 · Proxy Audit",
        "5 · Fairness & Explainability", "6 · Impact Assessment", "7 · Robustness & Autonomy",
        "8 · Case Library"]
SYSTEM = "Face recognition library"  # recorded on schema v2; generates synthetic media


def serve(script: str, port: int) -> subprocess.Popen:
    env = {**os.environ, "GEMINI_API_KEY": ""}
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", script, "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def settle(page: Page, ms: int = 1500) -> None:
    page.wait_for_timeout(300)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')",
                           timeout=60000)
    page.wait_for_timeout(ms)


def shoot(page: Page, name: str) -> None:
    """Full-page capture: grow the viewport to the app's content height."""
    height = page.evaluate(
        "() => Math.max(...['[data-testid=\"stMain\"]', '[data-testid=\"stAppViewContainer\"]', 'body']"
        ".map(s => document.querySelector(s)).filter(Boolean).map(e => e.scrollHeight))")
    page.set_viewport_size({"width": WIDTH, "height": min(max(int(height) + 40, 900), 7000)})
    settle(page, 800)
    page.screenshot(path=str(OUT / f"{name}.png"))
    page.set_viewport_size({"width": WIDTH, "height": 900})


def tab(page: Page, label: str) -> None:
    page.get_by_role("tab", name=label).click()
    settle(page)


def click(page: Page, name: str, last: bool = False) -> None:
    buttons = page.get_by_role("button", name=name)  # names include the icon ligature
    (buttons.last if last else buttons.first).click()
    settle(page)


def run_theme(browser, scheme: str) -> None:
    page = browser.new_page(viewport={"width": WIDTH, "height": 900}, color_scheme=scheme)
    page.goto(f"http://localhost:{APP_PORT}/")
    page.wait_for_selector("text=Try an example", timeout=60000)
    settle(page)
    for i, label in enumerate(TABS, start=1):  # nothing loaded
        tab(page, label)
        shoot(page, f"tab{i}_empty_{scheme}")
    tab(page, TABS[0])
    click(page, SYSTEM)
    shoot(page, f"tab1_loaded_{scheme}")
    tab(page, TABS[1])
    click(page, "UCI Adult income (6,000-row sample)")
    shoot(page, f"tab2_loaded_{scheme}")
    tab(page, TABS[2])
    shoot(page, f"tab3_loaded_{scheme}")
    tab(page, TABS[3])
    page.get_by_role("button", name="Change dataset").first.click()
    page.wait_for_timeout(600)
    click(page, "Cost-as-a-proxy demo (synthetic)", last=True)
    click(page, "Run reconstruction test")
    shoot(page, f"tab4_loaded_{scheme}")
    tab(page, TABS[4])
    click(page, "What if the README had disclosed human oversight and transparency?")
    shoot(page, f"tab5_loaded_{scheme}")
    for i in (6, 7, 8):
        tab(page, TABS[i - 1])
        shoot(page, f"tab{i}_loaded_{scheme}")
    page.close()
    # Out-of-scope verdict (hand-built facts until the military sample is recorded).
    page = browser.new_page(viewport={"width": WIDTH, "height": 900}, color_scheme=scheme)
    page.goto(f"http://localhost:{HARNESS_PORT}/")
    page.wait_for_selector("text=Why this tier", timeout=60000)
    settle(page)
    page.set_viewport_size({"width": WIDTH, "height": 900})
    page.screenshot(path=str(OUT / f"out_of_scope_verdict_{scheme}.png"))
    page.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    servers = [serve("app.py", APP_PORT), serve("scripts/screenshot_harness.py", HARNESS_PORT)]
    try:
        time.sleep(6)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("light", "dark"):
                run_theme(browser, scheme)
            browser.close()
    finally:
        for s in servers:
            s.terminate()
    print(f"wrote {len(list(OUT.glob('*.png')))} screenshots to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
