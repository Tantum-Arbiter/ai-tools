"""GitHub client for Day Job — Playwright-based read-only scraper.

SAFETY: This module contains ZERO methods that edit, delete, close,
reassign, or modify any GitHub resource. It can only navigate to pages
and read DOM content. There is no generic "run JS" or "click button"
method exposed. The LLM cannot instruct it to perform mutations.

Connection strategy (in order):
1. CDP — connects to the operator's Chrome if launched with
   --remote-debugging-port=9222 (reuses existing SSO session).
2. Persistent Chromium profile — falls back to Playwright's bundled
   Chromium with a persistent profile at ~/.arbiter/chromium-profile.
   First run opens a headed window for SSO login; subsequent runs
   are headless.

Sprint rollover is deferred until a safe browser-automation pattern
is confirmed with the operator.
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import re
from dataclasses import dataclass

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import GitHubConfig
from .safety import SafetyGate, Service

_log = logging.getLogger("dayjob.github_scraper")

_CDP_ENDPOINT = "http://127.0.0.1:9222"
_DEFAULT_PROFILE_DIR = pathlib.Path.home() / ".arbiter" / "chromium-profile"


@dataclass(frozen=True)
class Card:
    number: int
    title: str
    state: str
    labels: list[str]
    assignees: list[str]
    milestone: str | None
    url: str


@dataclass(frozen=True)
class ProjectItem:
    title: str
    number: int
    status: str
    squad: str
    stream: str
    estimates: str
    assignees: list[str]
    milestone: str
    labels: list[str]
    url: str


class GitHubScraper:
    """Read-only GitHub scraper. No edit/delete/close methods exist.

    Tries CDP first (Chrome with --remote-debugging-port=9222).
    Falls back to a persistent Chromium profile if CDP is unavailable.
    """

    def __init__(self, config: GitHubConfig, gate: SafetyGate) -> None:
        self._config = config
        self._gate = gate
        self._context: BrowserContext | None = None
        self._pw_instance = None
        self._owned_page: Page | None = None
        self._using_cdp = False
        profile = config.browser_profile_dir or str(_DEFAULT_PROFILE_DIR)
        self._profile_dir = pathlib.Path(profile)

    async def _get_page(self) -> Page:
        if self._owned_page and not self._owned_page.is_closed():
            return self._owned_page

        if self._context is None:
            pw = await async_playwright().start()
            self._pw_instance = pw

            try:
                browser = await pw.chromium.connect_over_cdp(_CDP_ENDPOINT)
                self._context = browser.contexts[0] if browser.contexts else await browser.new_context()
                self._using_cdp = True
                print(f"[DAYJOB] Connected to Chrome via CDP at {_CDP_ENDPOINT}")
            except Exception:
                print(
                    f"[DAYJOB] CDP unavailable — falling back to persistent Chromium "
                    f"profile at {self._profile_dir}"
                )
                self._profile_dir.mkdir(parents=True, exist_ok=True)
                marker = self._profile_dir / ".logged_in"
                print(f"[DAYJOB] Login marker exists: {marker.exists()} ({marker})")
                if not marker.exists():
                    await pw.stop()
                    self._pw_instance = None
                    raise ConnectionError(
                        "GitHub session not set up. Run this once from your terminal:\n"
                        "  cd arbiter-mission-control && ./venv/bin/python -m dayjob.login_setup"
                    )
                print("[DAYJOB] Launching Chromium headless with saved session")
                self._context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._profile_dir),
                    headless=True,
                    accept_downloads=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )

        self._owned_page = await self._context.new_page()
        return self._owned_page

    async def _mark_logged_in(self) -> None:
        if self._using_cdp:
            return
        marker = self._profile_dir / ".logged_in"
        if not marker.exists():
            marker.touch()
            _log.info("Marked profile as logged-in at %s", marker)

    async def close(self) -> None:
        if self._owned_page and not self._owned_page.is_closed():
            await self._owned_page.close()
            self._owned_page = None
        if self._context is not None and not self._using_cdp:
            await self._context.close()
            self._context = None
        if self._pw_instance is not None:
            await self._pw_instance.stop()
            self._pw_instance = None

    async def _wait_for_login(self, page: Page) -> None:
        if self._using_cdp:
            return
        current = page.url
        needs_login = (
            "/login" in current
            or "/sso" in current
            or self._config.base_url not in current
        )
        if needs_login:
            _log.warning(
                "GitHub login required (current URL: %s) — complete SSO in "
                "the Chromium window. Waiting up to 120s...",
                current,
            )
            for _ in range(120):
                await asyncio.sleep(1)
                url = page.url
                on_github = self._config.base_url in url
                past_login = "/login" not in url and "/sso" not in url
                if on_github and past_login:
                    _log.info("Login detected — continuing")
                    await self._mark_logged_in()
                    await asyncio.sleep(1)
                    return
            raise ConnectionError(
                "Timed out waiting for GitHub login. "
                "Complete SSO in the Chromium window and try again."
            )
        await self._mark_logged_in()

    async def search_epics(self, repo: str) -> list[Card]:
        self._gate.check(
            service=Service.GITHUB,
            operation="search_epics",
            params={"repo": repo},
        )
        url = (
            f"{self._config.base_url}/{self._config.org}/{repo}"
            f"/issues?q=is%3Aissue+label%3Aepic&state=all"
        )
        page = await self._get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._wait_for_login(page)
        await page.wait_for_selector("[data-testid='issue-row'], .js-issue-row, .Box-row", timeout=10000)
        return await self._extract_issue_rows(page)

    async def search_cards(
        self, repo: str, *, query: str = "", labels: str = ""
    ) -> list[Card]:
        self._gate.check(
            service=Service.GITHUB,
            operation="search_cards",
            params={"repo": repo, "query": query, "labels": labels},
        )
        search_parts = [f"repo:{self._config.org}/{repo}", "is:issue"]
        if query:
            search_parts.append(query)
        if labels:
            for label in labels.split(","):
                search_parts.append(f"label:{label.strip()}")
        q = "+".join(search_parts)
        url = f"{self._config.base_url}/search?q={q}&type=issues"
        page = await self._get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._wait_for_login(page)
        await asyncio.sleep(2)
        return await self._extract_search_results(page)

    async def get_project_items(self) -> list[ProjectItem]:
        self._gate.check(
            service=Service.GITHUB,
            operation="get_sprint_items",
            params={},
        )
        url = (
            f"{self._config.base_url}/orgs/{self._config.org}"
            f"/projects/{self._config.project_number}?layout=table"
        )
        page = await self._get_page()
        print(f"[DAYJOB] Navigating to project table: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._wait_for_login(page)
        print(f"[DAYJOB] Page loaded, URL: {page.url}")
        print(f"[DAYJOB] Page title: {await page.title()}")
        try:
            await page.wait_for_selector(
                "[role='row'], table tr", timeout=15000,
            )
            print("[DAYJOB] Table rows found")
        except Exception:
            print("[DAYJOB] WARNING: No table rows found after 15s")
            body_el = await page.query_selector("body")
            if body_el:
                body_text = (await body_el.inner_text())[:300]
                print(f"[DAYJOB] Page body preview: {body_text}")
        await asyncio.sleep(2)
        items = await self._scroll_and_extract(page)
        return items

    async def _scroll_and_extract(self, page: Page) -> list[ProjectItem]:
        seen_titles: set[str] = set()
        all_items: list[ProjectItem] = []
        max_rounds = 20

        grid = await page.query_selector("[role='grid'], table, [data-testid='TableRoot']")
        if grid:
            box = await grid.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                await page.mouse.move(cx, cy)
                print(f"[DAYJOB] Mouse positioned over grid at ({cx:.0f}, {cy:.0f})")

        for rnd in range(max_rounds):
            batch = await self._extract_project_rows(page)
            new_count = 0
            for item in batch:
                if item.title not in seen_titles:
                    seen_titles.add(item.title)
                    all_items.append(item)
                    new_count += 1
            print(f"[DAYJOB] Scroll round {rnd}: {len(batch)} visible, {new_count} new, {len(all_items)} total")
            if new_count == 0 or rnd == max_rounds - 1:
                break
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(1.5)
        print(f"[DAYJOB] Final total: {len(all_items)} unique project items")
        return all_items

    async def _extract_issue_rows(self, page: Page) -> list[Card]:
        rows = await page.query_selector_all(
            "[data-testid='issue-row'], .js-issue-row, .Box-row"
        )
        results: list[Card] = []
        for row in rows:
            title_el = await row.query_selector("a[data-hovercard-type='issue'], a.Link--primary, a.v-align-middle")
            if not title_el:
                continue
            title = (await title_el.inner_text()).strip()
            href = await title_el.get_attribute("href") or ""
            number = self._extract_number(href)
            label_els = await row.query_selector_all(".IssueLabel, .label, [data-name]")
            labels = []
            for lbl in label_els:
                label_text = (await lbl.inner_text()).strip()
                if label_text:
                    labels.append(label_text)
            assignee_els = await row.query_selector_all("a.avatar, img.avatar, [data-hovercard-type='user']")
            assignees = []
            for a in assignee_els:
                alt = await a.get_attribute("alt") or await a.get_attribute("aria-label") or ""
                if alt:
                    assignees.append(alt.lstrip("@"))
            state_el = await row.query_selector("[data-testid='issue-open-icon'], .octicon-issue-opened, .octicon-issue-closed")
            state = "open"
            if state_el:
                cls = await state_el.get_attribute("class") or ""
                if "closed" in cls:
                    state = "closed"
            results.append(Card(
                number=number,
                title=title,
                state=state,
                labels=labels,
                assignees=assignees,
                milestone=None,
                url=f"{self._config.base_url}{href}" if href.startswith("/") else href,
            ))
        return results

    async def _extract_search_results(self, page: Page) -> list[Card]:
        rows = await page.query_selector_all(".search-title a, .issue-list-item, [data-testid='search-result']")
        results: list[Card] = []
        for row in rows:
            title = (await row.inner_text()).strip()
            href = await row.get_attribute("href") or ""
            number = self._extract_number(href)
            if not title or number == 0:
                continue
            results.append(Card(
                number=number,
                title=title,
                state="open",
                labels=[],
                assignees=[],
                milestone=None,
                url=f"{self._config.base_url}{href}" if href.startswith("/") else href,
            ))
        return results

    async def _extract_project_rows(self, page: Page) -> list[ProjectItem]:
        header_row = await page.query_selector("[role='row']:first-child, thead tr")
        field_headers: list[str] = []
        if header_row:
            headers = await header_row.query_selector_all(
                "[role='columnheader'], [role='gridcell'], th"
            )
            for h in headers:
                text = (await h.inner_text()).strip().lower()
                field_headers.append(text)

        if "title" in field_headers:
            field_headers.remove("title")
        while field_headers and not field_headers[-1]:
            field_headers.pop()
        while field_headers and not field_headers[0]:
            field_headers.pop(0)

        field_map: dict[int, str] = {i: h for i, h in enumerate(field_headers)}
        print(f"[DAYJOB] Field headers (excl title): {field_map}")

        rows = await page.query_selector_all(
            "[role='row']:not(:first-child), tbody tr"
        )
        print(f"[DAYJOB] Data rows found: {len(rows)}")
        results: list[ProjectItem] = []
        skipped = 0
        for row_idx, row in enumerate(rows):
            row_header = await row.query_selector("[role='rowheader']")
            raw_title = ""
            href = ""
            if row_header:
                raw_title = (await row_header.inner_text()).strip()
                title_link = await row_header.query_selector("a[href*='/issues/'], a[href*='/pull/']")
                if title_link:
                    href = await title_link.get_attribute("href") or ""

            if not href:
                link_el = await row.query_selector("a[href*='/issues/']")
                if not link_el:
                    link_el = await row.query_selector("a[href*='/pull/']")
                if link_el:
                    href = await link_el.get_attribute("href") or ""
                    if not raw_title:
                        raw_title = (await link_el.inner_text()).strip()

            if not raw_title:
                skipped += 1
                continue

            cells = await row.query_selector_all("[role='gridcell'], td")
            cell_texts: list[str] = []
            for c in cells:
                cell_texts.append((await c.inner_text()).strip())

            while cell_texts and cell_texts[0].isdigit() and len(cell_texts[0]) <= 4:
                cell_texts.pop(0)
            while cell_texts and not cell_texts[-1]:
                cell_texts.pop()

            if row_idx == 0:
                print(f"[DAYJOB] Row 0 title: {raw_title[:60]}")
                print(f"[DAYJOB] Row 0 field cells ({len(cell_texts)}): {[t[:40] for t in cell_texts]}")

            def _field(name: str) -> str:
                for idx, col_name in field_map.items():
                    if name in col_name and idx < len(cell_texts):
                        return cell_texts[idx]
                return ""

            number = self._extract_number(href) or self._extract_number_from_title(raw_title)
            title = re.sub(r"\s*#\d+\s*$", "", raw_title).strip()

            status = _field("status")
            squad = _field("squad")
            stream = _field("stream")
            estimates = _field("estimate")
            milestone = _field("milestone")
            labels_raw = _field("label")
            labels = [
                lbl.strip()
                for lbl in re.split(r"[,\n]+", labels_raw)
                if lbl.strip()
            ]

            assignee_text = _field("assignee")
            assignees = [
                a.strip()
                for a in re.split(r"[,\n]+", assignee_text)
                if a.strip()
            ]

            url = ""
            if href:
                url = f"{self._config.base_url}{href}" if href.startswith("/") else href

            results.append(ProjectItem(
                title=title,
                number=number,
                status=status,
                squad=squad,
                stream=stream,
                estimates=estimates,
                assignees=assignees,
                milestone=milestone,
                labels=labels,
                url=url,
            ))
        if skipped:
            print(f"[DAYJOB] Skipped {skipped} empty rows")
        print(f"[DAYJOB] Extracted {len(results)} project items")
        return results

    @staticmethod
    def _extract_number_from_title(title: str) -> int:
        match = re.search(r"#(\d+)", title)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _extract_number(href: str) -> int:
        match = re.search(r"/issues/(\d+)", href)
        return int(match.group(1)) if match else 0
