"""Tyler EnerGov / ePermits portal adapter (Minnetonka reference impl).

The portal flow: Search Permit -> set Permit Type=Building, Work Type=Reroof,
date range -> click Excel export (green X) -> download.

This is a SKELETON. Selectors will need to be filled in against the live portal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


def scrape(city_config: dict[str, Any], download_dir: Path) -> Path:
    """Run the scrape and return the path to the downloaded XLSX."""
    pcfg = city_config["portal_config"]
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        page.goto(pcfg["url"], wait_until="networkidle")
        # TODO: navigate to search page (selectors vary by Tyler portal version)
        # page.click("text=Search Permit")
        # page.fill("input[name=permitType]", pcfg["filters"]["permit_type"])
        # page.fill("input[name=workType]", pcfg["filters"]["work_type"])
        # page.click("button:has-text('Search')")
        # page.wait_for_selector(".results-table")

        # with page.expect_download() as dl_info:
        #     page.click("a[title='Export to Excel']")
        # download = dl_info.value
        # out = download_dir / download.suggested_filename
        # download.save_as(out)

        # Screenshot on every run for health checks
        page.screenshot(path=str(download_dir / "last_run.png"), full_page=True)
        browser.close()

    raise NotImplementedError(
        "Fill in Tyler portal selectors after inspecting the live Minnetonka site."
    )
