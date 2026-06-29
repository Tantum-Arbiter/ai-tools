"""Board configuration — defines what to observe on each project board.

This is the page-object model. Each board config tells the observer
what URL to navigate to, what columns to expect, and what selectors
to use for extraction. Think of it as the fixture for an E2E test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ColumnDef:
    name: str
    type: str = "text"


@dataclass(frozen=True)
class ViewDef:
    name: str
    layout: str = "table"
    view_id: str = ""

    @property
    def url_params(self) -> str:
        params = f"layout={self.layout}"
        if self.view_id:
            params += f"&viewId={self.view_id}"
        return params


@dataclass(frozen=True)
class BoardDef:
    name: str
    org: str
    project_number: int
    base_url: str = "https://github.com"
    views: list[ViewDef] = field(default_factory=lambda: [ViewDef(name="default")])
    columns: list[ColumnDef] = field(default_factory=list)
    known_labels: list[str] = field(default_factory=list)
    known_statuses: list[str] = field(default_factory=list)

    @property
    def project_url(self) -> str:
        return f"{self.base_url}/orgs/{self.org}/projects/{self.project_number}"

    def view_url(self, view_name: str = "default") -> str:
        for v in self.views:
            if v.name == view_name:
                return f"{self.project_url}?{v.url_params}"
        return f"{self.project_url}?layout=table"


@dataclass
class BoardsConfig:
    boards: dict[str, BoardDef] = field(default_factory=dict)
    browser_profile_dir: str = ""


def load_boards_config(path: Path) -> BoardsConfig:
    if not path.exists():
        return BoardsConfig()

    raw = yaml.safe_load(path.read_text()) or {}
    boards: dict[str, BoardDef] = {}

    for board_key, board_data in raw.get("boards", {}).items():
        views = [
            ViewDef(
                name=v.get("name", "default"),
                layout=v.get("layout", "table"),
                view_id=str(v.get("view_id", "")),
            )
            for v in board_data.get("views", [{"name": "default"}])
        ]
        columns = [
            ColumnDef(
                name=c.get("name", ""),
                type=c.get("type", "text"),
            )
            for c in board_data.get("columns", [])
        ]
        boards[board_key] = BoardDef(
            name=board_data.get("name", board_key),
            org=board_data.get("org", ""),
            project_number=int(board_data.get("project_number", 0)),
            base_url=board_data.get("base_url", "https://github.com"),
            views=views,
            columns=columns,
            known_labels=board_data.get("known_labels", []),
            known_statuses=board_data.get("known_statuses", []),
        )

    return BoardsConfig(
        boards=boards,
        browser_profile_dir=raw.get("browser_profile_dir", ""),
    )
