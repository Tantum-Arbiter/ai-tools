"""GitHub API client for Day Job — PAT-based, read-only.

SAFETY: This module contains ZERO methods that edit, delete, close,
reassign, or modify any GitHub resource. Every method calls
gate.check() before executing. The PAT should have repo(read) scope
only — never repo(write).

Uses the repo Issues list endpoint (GET /repos/{org}/{repo}/issues)
instead of the Search API because EMU orgs block classic PATs from
the /search/issues endpoint.
"""
from __future__ import annotations

import logging

import httpx

from .config import GitHubConfig
from .github_client import Card, ProjectItem
from .safety import SafetyGate, Service

_GRAPHQL_URL = "https://api.github.com/graphql"
_REST_URL = "https://api.github.com"
_log = logging.getLogger("dayjob.github_api")

_PROJECT_ITEMS_QUERY = """
query($org: String!, $number: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2Field { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2Field { name } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field { ... on ProjectV2IterationField { name } }
              }
            }
          }
          content {
            ... on Issue {
              title
              number
              url
              state
              milestone { title }
              assignees(first: 5) { nodes { login } }
              labels(first: 10) { nodes { name } }
            }
            ... on DraftIssue { title }
          }
        }
      }
    }
  }
}
"""


class GitHubAPIClient:
    """Read-only GitHub client using PAT + REST/GraphQL API.

    No edit/delete/close methods exist. The LLM cannot instruct
    mutations through this client.
    """

    def __init__(self, config: GitHubConfig, gate: SafetyGate, pat: str) -> None:
        self._config = config
        self._gate = gate
        self._headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def search_epics(self, repo: str) -> list[Card]:
        self._gate.check(
            service=Service.GITHUB,
            operation="search_epics",
            params={"repo": repo},
        )
        return await self._list_issues(repo, labels_filter=["epic"])

    async def search_cards(
        self, repo: str, *, query: str = "", labels: str = ""
    ) -> list[Card]:
        self._gate.check(
            service=Service.GITHUB,
            operation="search_cards",
            params={"repo": repo, "query": query, "labels": labels},
        )
        label_list: list[str] = []
        if labels:
            label_list = [lb.strip() for lb in labels.split(",") if lb.strip()]
        cards = await self._list_issues(repo, labels_filter=label_list)
        if query:
            needle = query.lower()
            cards = [c for c in cards if needle in c.title.lower()]
        return cards

    async def get_project_items(self) -> list[ProjectItem]:
        self._gate.check(
            service=Service.GITHUB,
            operation="get_sprint_items",
            params={},
        )
        all_nodes: list[dict] = []
        cursor: str | None = None
        print(f"[DAYJOB-API] Fetching project items for org={self._config.org} project={self._config.project_number}")
        async with httpx.AsyncClient(timeout=30) as client:
            for page_num in range(10):
                variables: dict = {
                    "org": self._config.org,
                    "number": self._config.project_number,
                    "cursor": cursor,
                }
                resp = await client.post(
                    _GRAPHQL_URL,
                    headers=self._headers,
                    json={"query": _PROJECT_ITEMS_QUERY, "variables": variables},
                )
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    print(f"[DAYJOB-API] GraphQL errors: {data['errors']}")
                    break
                items_data = (
                    data.get("data", {})
                    .get("organization", {})
                    .get("projectV2", {})
                    .get("items", {})
                )
                nodes = items_data.get("nodes", [])
                all_nodes.extend(nodes)
                page_info = items_data.get("pageInfo", {})
                print(f"[DAYJOB-API] Page {page_num}: {len(nodes)} items, hasNext={page_info.get('hasNextPage')}")
                if not page_info.get("hasNextPage"):
                    break
                cursor = page_info.get("endCursor")
        print(f"[DAYJOB-API] Total fetched: {len(all_nodes)} items")
        results = [self._parse_node(n) for n in all_nodes if n.get("content")]
        print(f"[DAYJOB-API] Parsed: {len(results)} project items (skipped {len(all_nodes) - len(results)} without content)")
        return results

    @staticmethod
    def _parse_node(node: dict) -> ProjectItem:
        content = node.get("content", {})
        title = content.get("title", "")
        number = content.get("number", 0)
        url = content.get("url", "")
        milestone_data = content.get("milestone")
        milestone = milestone_data.get("title", "") if milestone_data else ""
        assignees_nodes = content.get("assignees", {}).get("nodes", [])
        assignees = [a.get("login", "") for a in assignees_nodes]
        label_nodes = content.get("labels", {}).get("nodes", [])
        labels = [lb.get("name", "") for lb in label_nodes]

        fields: dict[str, str] = {}
        for fv in node.get("fieldValues", {}).get("nodes", []):
            field_info = fv.get("field", {})
            field_name = field_info.get("name", "").lower()
            if not field_name:
                continue
            if "name" in fv and fv["name"]:
                fields[field_name] = fv["name"]
            elif "text" in fv and fv["text"]:
                fields[field_name] = fv["text"]
            elif "number" in fv and fv["number"] is not None:
                num = fv["number"]
                fields[field_name] = str(int(num)) if num == int(num) else str(num)
            elif "title" in fv and fv["title"]:
                fields[field_name] = fv["title"]

        return ProjectItem(
            title=title,
            number=number,
            status=fields.get("status", ""),
            squad=fields.get("squad", ""),
            stream=fields.get("stream", ""),
            estimates=fields.get("estimates", fields.get("estimate", "")),
            assignees=assignees,
            milestone=milestone,
            labels=labels,
            url=url,
        )

    async def close(self) -> None:
        pass

    async def _list_issues(
        self, repo: str, *, labels_filter: list[str] | None = None
    ) -> list[Card]:
        url = f"{_REST_URL}/repos/{self._config.org}/{repo}/issues"
        params: dict[str, str | int] = {
            "state": "all",
            "per_page": 100,
        }
        if labels_filter:
            params["labels"] = ",".join(labels_filter)

        all_items: list[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            page_url: str | None = url
            while page_url:
                resp = await client.get(
                    page_url,
                    headers=self._headers,
                    params=params if page_url == url else None,
                )
                if resp.status_code != 200:
                    body = resp.text[:500]
                    _log.error(
                        "GitHub issues list failed: %d %s — %s",
                        resp.status_code, resp.reason_phrase, body,
                    )
                    resp.raise_for_status()
                all_items.extend(resp.json())
                page_url = resp.links.get("next", {}).get("url")
                if len(all_items) >= 300:
                    break

        results: list[Card] = []
        for item in all_items:
            if "pull_request" in item:
                continue
            labels = [lb.get("name", "") for lb in item.get("labels", [])]
            assignees = [a.get("login", "") for a in item.get("assignees", [])]
            milestone = item.get("milestone")
            ms_title = milestone.get("title") if milestone else None
            results.append(Card(
                number=item.get("number", 0),
                title=item.get("title", ""),
                state=item.get("state", "open"),
                labels=labels,
                assignees=assignees,
                milestone=ms_title,
                url=item.get("html_url", ""),
            ))
        return results
