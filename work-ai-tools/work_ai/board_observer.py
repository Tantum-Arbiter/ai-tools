"""Board observer — E2E-style read-only scraper for GitHub Projects.

Follows the same flow as a Playwright E2E test:
  1. Navigate to the board URL
  2. Wait for the table to render
  3. Read active filters (what's already applied)
  4. Read column headers (what fields are visible)
  5. Scroll through rows and extract data
  6. Return a snapshot of everything observed

No clicks, no form fills, no mutations. Pure observation.
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import re
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page, async_playwright

from .board_config import BoardDef

_log = logging.getLogger("work_ai.observer")

_CDP_ENDPOINT = "http://127.0.0.1:9222"
_DEFAULT_PROFILE_DIR = pathlib.Path.home() / ".work-ai" / "chromium-profile"


@dataclass
class BoardSnapshot:
    board_name: str
    view_name: str
    url: str
    active_filters: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    total_visible: int = 0


class BoardObserver:
    """Read-only observer. No click/fill/evaluate methods exist."""

    def __init__(self, profile_dir: str = "") -> None:
        self._profile_dir = pathlib.Path(profile_dir) if profile_dir else _DEFAULT_PROFILE_DIR
        self._context: BrowserContext | None = None
        self._pw_instance = None
        self._page: Page | None = None
        self._using_cdp = False

    async def _get_page(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page

        if self._context is None:
            pw = await async_playwright().start()
            self._pw_instance = pw

            try:
                browser = await pw.chromium.connect_over_cdp(_CDP_ENDPOINT)
                self._context = browser.contexts[0] if browser.contexts else await browser.new_context()
                self._using_cdp = True
                print("[WORK-AI] Connected via CDP")
            except Exception:
                print(f"[WORK-AI] CDP unavailable — using profile at {self._profile_dir}")
                self._profile_dir.mkdir(parents=True, exist_ok=True)
                marker = self._profile_dir / ".logged_in"
                if not marker.exists():
                    await pw.stop()
                    self._pw_instance = None
                    raise ConnectionError(
                        "Browser session not set up. Run login_setup first."
                    )
                self._context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._profile_dir),
                    headless=True,
                    accept_downloads=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )

        self._page = await self._context.new_page()
        return self._page

    async def observe(self, board: BoardDef, view_name: str = "default") -> BoardSnapshot:
        url = board.view_url(view_name)
        page = await self._get_page()

        print(f"[WORK-AI] Step 1: Navigate → {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        print("[WORK-AI] Step 2: Wait for table")
        try:
            await page.wait_for_selector("[role='row'], table tr", timeout=15000)
        except Exception:
            print("[WORK-AI] WARNING: No table rows found after 15s")
            return BoardSnapshot(board_name=board.name, view_name=view_name, url=url)

        await asyncio.sleep(2)

        print("[WORK-AI] Step 3: Read active filters")
        active_filters = await self._read_filters(page)

        print("[WORK-AI] Step 4: Read column headers")
        columns = await self._read_columns(page)

        print("[WORK-AI] Step 5: Scroll and extract rows")
        rows = await self._read_all_rows(page, columns)

        snapshot = BoardSnapshot(
            board_name=board.name,
            view_name=view_name,
            url=url,
            active_filters=active_filters,
            columns=columns,
            rows=rows,
            total_visible=len(rows),
        )
        print(f"[WORK-AI] Step 6: Done — {len(rows)} rows, {len(columns)} columns, {len(active_filters)} filters")
        return snapshot

    async def close(self) -> None:
        if self._page and not self._page.is_closed():
            await self._page.close()
            self._page = None
        if self._context is not None and not self._using_cdp:
            await self._context.close()
            self._context = None
        if self._pw_instance is not None:
            await self._pw_instance.stop()
            self._pw_instance = None

    async def _read_filters(self, page: Page) -> list[str]:
        """Read filter chips/pills from the toolbar — whatever's already applied."""
        filters: list[str] = []
        filter_els = await page.query_selector_all(
            "[data-testid='filter-item'], "
            ".filter-item, "
            "[aria-label*='Filter'], "
            ".TableFilterButton, "
            "[data-testid='slice-filter-label']"
        )
        for el in filter_els:
            text = (await el.inner_text()).strip()
            if text:
                filters.append(text)
        if not filters:
            toolbar = await page.query_selector(
                "[data-testid='project-view-toolbar'], "
                ".project-header, "
                "[role='toolbar']"
            )
            if toolbar:
                toolbar_text = (await toolbar.inner_text()).strip()
                filter_match = re.findall(r"(?:Filter|Filtered by|Slice by)[:\s]*(.+?)(?:\n|$)", toolbar_text, re.IGNORECASE)
                filters.extend(filter_match)
        print(f"[WORK-AI]   Filters found: {filters}")
        return filters

    async def _read_columns(self, page: Page) -> list[str]:
        """Read column headers from the first row."""
        columns: list[str] = []
        header_row = await page.query_selector("[role='row']:first-child, thead tr")
        if not header_row:
            return columns
        headers = await header_row.query_selector_all(
            "[role='columnheader'], th"
        )
        for h in headers:
            text = (await h.inner_text()).strip().lower()
            if text:
                columns.append(text)
        if "title" in columns:
            columns.remove("title")
        while columns and not columns[-1]:
            columns.pop()
        while columns and not columns[0]:
            columns.pop(0)
        print(f"[WORK-AI]   Columns: {columns}")
        return columns

    async def _read_all_rows(self, page: Page, columns: list[str]) -> list[dict[str, str]]:
        """Scroll through the table and extract all unique rows."""
        seen_titles: set[str] = set()
        all_rows: list[dict[str, str]] = []

        grid = await page.query_selector("[role='grid'], table, [data-testid='TableRoot']")
        if grid:
            box = await grid.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                await page.mouse.move(cx, cy)

        for rnd in range(20):
            batch = await self._extract_visible_rows(page, columns)
            new_count = 0
            for row in batch:
                title = row.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_rows.append(row)
                    new_count += 1
            print(f"[WORK-AI]   Scroll round {rnd}: {len(batch)} visible, {new_count} new, {len(all_rows)} total")
            if new_count == 0 or rnd == 19:
                break
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(1.5)
        return all_rows

    async def _extract_visible_rows(self, page: Page, columns: list[str]) -> list[dict[str, str]]:
        """Extract all currently visible rows from the DOM."""
        rows = await page.query_selector_all(
            "[role='row']:not(:first-child), tbody tr"
        )
        results: list[dict[str, str]] = []
        col_map = {i: name for i, name in enumerate(columns)}

        for row in rows:
            row_header = await row.query_selector("[role='rowheader']")
            title = ""
            link = ""
            number = ""

            if row_header:
                title = (await row_header.inner_text()).strip()
                title_link = await row_header.query_selector("a[href*='/issues/'], a[href*='/pull/']")
                if title_link:
                    link = await title_link.get_attribute("href") or ""

            if not link:
                link_el = await row.query_selector("a[href*='/issues/'], a[href*='/pull/']")
                if link_el:
                    link = await link_el.get_attribute("href") or ""
                    if not title:
                        title = (await link_el.inner_text()).strip()

            if not title:
                continue

            num_match = re.search(r"#(\d+)", title)
            if num_match:
                number = num_match.group(1)
                title = re.sub(r"\s*#\d+\s*$", "", title).strip()

            if not number and link:
                num_match = re.search(r"/issues/(\d+)", link)
                if num_match:
                    number = num_match.group(1)

            cells = await row.query_selector_all("[role='gridcell'], td")
            cell_texts: list[str] = []
            for c in cells:
                cell_texts.append((await c.inner_text()).strip())

            while cell_texts and cell_texts[0].isdigit() and len(cell_texts[0]) <= 4:
                cell_texts.pop(0)
            while cell_texts and not cell_texts[-1]:
                cell_texts.pop()

            row_data: dict[str, str] = {
                "title": title,
                "number": number,
                "url": link,
            }

            for idx, col_name in col_map.items():
                if idx < len(cell_texts):
                    row_data[col_name] = cell_texts[idx]

            results.append(row_data)
        return results
