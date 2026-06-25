"""Monday.com client — PERMANENTLY READ ONLY.

No write methods exist on this class. No generic query method exists.
The API token is stored internally and NEVER exposed via any public
method, property, or return value.

Even if the token were leaked, it is scoped to boards:read only —
the Monday.com API would reject any mutation at the token level.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import MondayConfig
from .safety import SafetyGate, Service


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    state: str
    groups: list[Group]


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    color: str


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    group: str
    state: str
    assignees: list[str]
    status: str
    date: str | None
    timeline_start: str | None
    timeline_end: str | None
    updated_at: str


@dataclass(frozen=True)
class Update:
    id: str
    body: str
    author: str
    created_at: str


class MondayClient:
    """Named-method-only Monday.com client. PERMANENTLY READ ONLY.

    There are no write methods. There is no generic query method.
    """

    def __init__(self, config: MondayConfig, gate: SafetyGate) -> None:
        self._config = config
        self._gate = gate
        self._headers = {
            "Authorization": config.api_token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }

    async def get_boards(self) -> list[Board]:
        self._gate.check(service=Service.MONDAY, operation="get_boards")
        query = """
        query($ids: [ID!]) {
          boards(ids: $ids) {
            id name state
            groups { id title color }
          }
        }
        """
        data = await self._query(query, {"ids": self._config.board_ids})
        return [
            Board(
                id=b["id"],
                name=b["name"],
                state=b["state"],
                groups=[
                    Group(id=g["id"], title=g["title"], color=g["color"])
                    for g in b.get("groups", [])
                ],
            )
            for b in data.get("data", {}).get("boards", [])
        ]

    async def get_items(self, board_id: str) -> list[Item]:
        self._gate.check(
            service=Service.MONDAY,
            operation="get_items",
            params={"board_id": board_id},
        )
        query = """
        query($boardId: [ID!]!) {
          boards(ids: $boardId) {
            items_page(limit: 200) {
              items {
                id name state group { id title }
                updated_at
                column_values {
                  id text value
                }
              }
            }
          }
        }
        """
        data = await self._query(query, {"boardId": [board_id]})
        boards = data.get("data", {}).get("boards", [])
        if not boards:
            return []
        raw_items = boards[0].get("items_page", {}).get("items", [])
        return [self._parse_item(i) for i in raw_items]

    async def get_updates(self, item_id: str, *, limit: int = 10) -> list[Update]:
        self._gate.check(
            service=Service.MONDAY,
            operation="get_updates",
            params={"item_id": item_id},
        )
        query = """
        query($ids: [ID!]) {
          items(ids: $ids) {
            updates(limit: 10) {
              id body
              creator { name }
              created_at
            }
          }
        }
        """
        data = await self._query(query, {"ids": [item_id]})
        items = data.get("data", {}).get("items", [])
        if not items:
            return []
        return [
            Update(
                id=u["id"],
                body=u.get("body") or "",
                author=u.get("creator", {}).get("name", "unknown"),
                created_at=u["created_at"],
            )
            for u in items[0].get("updates", [])
        ]

    async def search_items(self, board_id: str, *, query_text: str) -> list[Item]:
        self._gate.check(
            service=Service.MONDAY,
            operation="search_items",
            params={"board_id": board_id, "query_text": query_text},
        )
        all_items = await self.get_items(board_id)
        lower_q = query_text.lower()
        return [i for i in all_items if lower_q in i.name.lower()]

    @staticmethod
    def _parse_item(raw: dict[str, object]) -> Item:
        group = raw.get("group", {}) or {}
        columns = {
            c["id"]: c.get("text") or ""
            for c in raw.get("column_values", [])  # type: ignore[union-attr]
        }
        assignees: list[str] = []
        person_col = columns.get("person") or columns.get("people") or ""
        if person_col:
            assignees = [p.strip() for p in person_col.split(",") if p.strip()]
        return Item(
            id=raw["id"],  # type: ignore[arg-type]
            name=raw.get("name") or "",  # type: ignore[arg-type]
            group=group.get("title") or "",  # type: ignore[union-attr,arg-type]
            state=raw.get("state") or "",  # type: ignore[arg-type]
            assignees=assignees,
            status=columns.get("status") or "",
            date=columns.get("date") or None,
            timeline_start=columns.get("timeline", {}).get("from") if isinstance(columns.get("timeline"), dict) else None,  # type: ignore[union-attr]
            timeline_end=columns.get("timeline", {}).get("to") if isinstance(columns.get("timeline"), dict) else None,  # type: ignore[union-attr]
            updated_at=raw.get("updated_at") or "",  # type: ignore[arg-type]
        )

    async def _query(
        self, query: str, variables: dict[str, object]
    ) -> dict[str, object]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._config.api_url,
                headers=self._headers,
                json={"query": query, "variables": variables},
                timeout=30.0,
            )
            resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
