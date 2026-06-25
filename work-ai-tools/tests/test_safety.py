"""Tests for the Day Job safety gate — defence-in-depth enforcement.

Verifies:
- Read operations pass without confirmation
- Unlisted operations are hard-blocked (edit/delete/close/reassign)
- GitHub has ZERO write operations (scraper is read-only)
- Monday.com has ZERO write operations
- Scraper/client classes have no mutation methods and no dangerous imports
- Every client method calls _gate.check() before executing
- Routes are GET-only — no POST/PUT/DELETE/PATCH
- Allowlist and client methods stay in sync
- Gated writes on other services require valid confirmation tokens
- Tokens cannot be forged, reused across operations, or used after expiry
- Audit log records every check including needs_confirmation and confirmed
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from work_ai.safety import (
    ConfirmationRequiredError,
    ConfirmationSigner,
    InvalidConfirmationError,
    OPERATION_ALLOWLIST,
    OperationBlockedError,
    SafetyAuditLog,
    SafetyGate,
    Service,
    Tier,
    hash_params,
)

_SECRET = b"test-secret-for-dayjob-safety-32-bytes!"
_NOW = 1719300000.0


@pytest.fixture
def audit(tmp_path: Path) -> SafetyAuditLog:
    return SafetyAuditLog(tmp_path, clock=lambda: _NOW)


@pytest.fixture
def signer() -> ConfirmationSigner:
    return ConfirmationSigner(_SECRET)


@pytest.fixture
def under_test(signer: ConfirmationSigner, audit: SafetyAuditLog) -> SafetyGate:
    return SafetyGate(signer, audit, clock=lambda: _NOW)


class TestReadOperationsPassThrough:
    @pytest.mark.parametrize("service,operation", [
        (Service.MONDAY, "get_boards"),
        (Service.MONDAY, "get_items"),
        (Service.MONDAY, "get_updates"),
        (Service.MONDAY, "search_items"),
        (Service.GITHUB, "search_epics"),
        (Service.GITHUB, "search_cards"),
        (Service.GITHUB, "get_sprint_items"),
    ])
    def test_read_operations_pass_without_confirmation(
        self, under_test: SafetyGate, service: Service, operation: str,
    ) -> None:
        under_test.check(service=service, operation=operation)


class TestUnlistedOperationsBlocked:
    @pytest.mark.parametrize("service,operation", [
        (Service.MONDAY, "create_item"),
        (Service.MONDAY, "update_item"),
        (Service.MONDAY, "delete_item"),
        (Service.MONDAY, "archive_board"),
        (Service.MONDAY, "move_item"),
        (Service.MONDAY, "change_column_value"),
        (Service.GITHUB, "create_issue"),
        (Service.GITHUB, "close_issue"),
        (Service.GITHUB, "delete_issue"),
        (Service.GITHUB, "update_issue"),
        (Service.GITHUB, "add_label"),
        (Service.GITHUB, "reassign"),
        (Service.GITHUB, "set_item_iteration"),
        (Service.GITHUB, "merge_pull_request"),
        (Service.GITHUB, "create_comment"),
        (Service.GITHUB, "delete_comment"),
        (Service.SLACK, "delete_message"),
        (Service.SLACK, "edit_message"),
    ])
    def test_unlisted_operation_raises_blocked(
        self, under_test: SafetyGate, service: Service, operation: str,
    ) -> None:
        with pytest.raises(OperationBlockedError):
            under_test.check(service=service, operation=operation)

    def test_completely_unknown_service_operation_blocked(
        self, under_test: SafetyGate,
    ) -> None:
        with pytest.raises(OperationBlockedError):
            under_test.check(service=Service.MONDAY, operation="invented_operation_xyz")

    def test_empty_string_operation_blocked(
        self, under_test: SafetyGate,
    ) -> None:
        with pytest.raises(OperationBlockedError):
            under_test.check(service=Service.GITHUB, operation="")


class TestMondayHasZeroWriteOperations:
    def test_no_monday_write_operations_in_allowlist(self) -> None:
        monday_ops = {
            (svc, op): tier
            for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if svc == Service.MONDAY
        }

        for (svc, op), tier in monday_ops.items():
            assert tier == Tier.READ, (
                f"Monday.com operation '{op}' has tier {tier} — "
                f"Monday.com must be PERMANENTLY READ ONLY"
            )


class TestGitHubHasZeroWriteOperations:
    def test_no_github_write_operations_in_allowlist(self) -> None:
        github_ops = {
            (svc, op): tier
            for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if svc == Service.GITHUB
        }

        for (svc, op), tier in github_ops.items():
            assert tier == Tier.READ, (
                f"GitHub operation '{op}' has tier {tier} — "
                f"GitHub scraper must be READ ONLY"
            )


class TestGatedWriteRequiresConfirmation:
    def test_gated_write_without_token_raises(
        self, under_test: SafetyGate,
    ) -> None:
        with pytest.raises(ConfirmationRequiredError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
            )

    def test_gated_write_with_valid_token_passes(
        self, under_test: SafetyGate,
    ) -> None:
        params = {"channel": "general", "text": "hello"}
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params=params,
        )

        under_test.check(
            service=Service.SLACK,
            operation="send_message",
            params=params,
            confirmation_token=token,
        )

    def test_forged_token_rejected(self, under_test: SafetyGate) -> None:
        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
                params={"channel": "general"},
                confirmation_token="forged-token-value",
            )

    def test_token_for_wrong_operation_rejected(
        self, under_test: SafetyGate,
    ) -> None:
        params = {"channel": "general", "text": "hello"}
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params=params,
        )

        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.CLARITY,
                operation="fill_timesheet",
                params=params,
                confirmation_token=token,
            )

    def test_token_for_wrong_service_same_operation_rejected(
        self, under_test: SafetyGate,
    ) -> None:
        params = {"file": "report.pptx"}
        token = under_test.mint_confirmation(
            service=Service.SHAREPOINT,
            operation="upload_ppt",
            params=params,
        )

        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.CLARITY,
                operation="fill_timesheet",
                params=params,
                confirmation_token=token,
            )

    def test_token_for_different_params_rejected(
        self, under_test: SafetyGate,
    ) -> None:
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params={"channel": "general"},
        )

        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
                params={"channel": "random"},
                confirmation_token=token,
            )

    def test_token_with_extra_params_rejected(
        self, under_test: SafetyGate,
    ) -> None:
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params={"channel": "general"},
        )

        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
                params={"channel": "general", "extra": "injected"},
                confirmation_token=token,
            )

    def test_token_with_empty_params_vs_none_rejected(
        self, under_test: SafetyGate,
    ) -> None:
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params={"key": "value"},
        )

        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
                params={},
                confirmation_token=token,
            )

    def test_expired_token_rejected(
        self, signer: ConfirmationSigner, audit: SafetyAuditLog,
    ) -> None:
        expired_time = _NOW + 200.0
        gate = SafetyGate(signer, audit, clock=lambda: expired_time)
        params = {"channel": "general"}
        token = signer.mint(
            service=Service.SLACK,
            operation="send_message",
            params_hash=hash_params(params),
            now=_NOW,
        )

        with pytest.raises(InvalidConfirmationError, match="expired"):
            gate.check(
                service=Service.SLACK,
                operation="send_message",
                params=params,
                confirmation_token=token,
            )

    def test_token_at_exact_expiry_boundary_rejected(
        self, signer: ConfirmationSigner, audit: SafetyAuditLog,
    ) -> None:
        boundary_time = _NOW + 121.0
        gate = SafetyGate(signer, audit, clock=lambda: boundary_time)
        params = {"channel": "general"}
        token = signer.mint(
            service=Service.SLACK,
            operation="send_message",
            params_hash=hash_params(params),
            now=_NOW,
        )

        with pytest.raises(InvalidConfirmationError, match="expired"):
            gate.check(
                service=Service.SLACK,
                operation="send_message",
                params=params,
                confirmation_token=token,
            )

    @pytest.mark.parametrize("gated_service,gated_op", [
        (Service.SLACK, "send_message"),
        (Service.CLARITY, "fill_timesheet"),
        (Service.CLARITY, "submit_timesheet"),
        (Service.SHAREPOINT, "upload_ppt"),
    ])
    def test_all_gated_writes_require_confirmation(
        self, under_test: SafetyGate, gated_service: Service, gated_op: str,
    ) -> None:
        with pytest.raises(ConfirmationRequiredError):
            under_test.check(service=gated_service, operation=gated_op)


class TestCannotMintForReadOnlyService:
    @pytest.mark.parametrize("service,operation", [
        (Service.MONDAY, "get_boards"),
        (Service.MONDAY, "get_items"),
        (Service.MONDAY, "get_updates"),
        (Service.MONDAY, "search_items"),
        (Service.GITHUB, "search_epics"),
        (Service.GITHUB, "search_cards"),
        (Service.GITHUB, "get_sprint_items"),
    ])
    def test_cannot_mint_confirmation_for_read_only_operations(
        self, under_test: SafetyGate, service: Service, operation: str,
    ) -> None:
        from work_ai.safety import SafetyError

        with pytest.raises(SafetyError, match="not a gated write"):
            under_test.mint_confirmation(service=service, operation=operation)

    def test_cannot_mint_for_unlisted_operation(
        self, under_test: SafetyGate,
    ) -> None:
        from work_ai.safety import SafetyError

        with pytest.raises(SafetyError):
            under_test.mint_confirmation(
                service=Service.GITHUB,
                operation="delete_issue",
            )


class TestAuditLogRecordsEverything:
    def test_read_operation_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        under_test.check(service=Service.MONDAY, operation="get_boards")

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["service"] == "monday"
        assert entry["operation"] == "get_boards"
        assert entry["tier"] == "read"
        assert entry["result"] == "ok"

    def test_blocked_operation_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        with pytest.raises(OperationBlockedError):
            under_test.check(service=Service.MONDAY, operation="delete_item")

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["result"] == "blocked"

    def test_needs_confirmation_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        with pytest.raises(ConfirmationRequiredError):
            under_test.check(service=Service.SLACK, operation="send_message")

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["service"] == "slack"
        assert entry["operation"] == "send_message"
        assert entry["tier"] == "gated_write"
        assert entry["result"] == "needs_confirmation"

    def test_confirmed_write_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        params = {"channel": "general", "text": "hi"}
        token = under_test.mint_confirmation(
            service=Service.SLACK,
            operation="send_message",
            params=params,
        )
        under_test.check(
            service=Service.SLACK,
            operation="send_message",
            params=params,
            confirmation_token=token,
        )

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["service"] == "slack"
        assert entry["operation"] == "send_message"
        assert entry["tier"] == "gated_write"
        assert entry["result"] == "confirmed"

    def test_invalid_token_attempt_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        with pytest.raises(InvalidConfirmationError):
            under_test.check(
                service=Service.SLACK,
                operation="send_message",
                params={"channel": "general"},
                confirmation_token="bad-token",
            )

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["service"] == "slack"
        assert entry["operation"] == "send_message"
        assert entry["tier"] == "gated_write"
        assert entry["result"] == "invalid_token"

    def test_multiple_operations_all_logged(
        self, under_test: SafetyGate, tmp_path: Path,
    ) -> None:
        under_test.check(service=Service.MONDAY, operation="get_boards")
        under_test.check(service=Service.GITHUB, operation="search_epics")
        with pytest.raises(OperationBlockedError):
            under_test.check(service=Service.GITHUB, operation="delete_issue")

        log_files = list(tmp_path.glob("dayjob-audit-*.jsonl"))
        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 3


DANGEROUS_METHOD_NAMES = {
    "create_issue", "close_issue", "delete_issue", "update_issue",
    "add_label", "remove_label", "reassign", "merge_pull_request",
    "create_comment", "delete_comment", "edit_comment",
    "set_item_iteration", "move_card", "archive_card",
    "lock_issue", "unlock_issue", "transfer_issue",
}

DANGEROUS_MONDAY_METHOD_NAMES = {
    "create_item", "update_item", "delete_item", "archive_board",
    "move_item", "change_column_value", "create_update",
    "delete_update", "archive_item", "duplicate_board",
    "execute_query", "run_query", "raw_query", "mutate",
}

MUTATING_PLAYWRIGHT_PATTERNS = [
    "page.click(", "page.dblclick(", "page.fill(", "page.type(",
    "page.press(", "page.check(", "page.uncheck(",
    "page.select_option(", "page.set_input_files(",
    "page.dispatch_event(", "page.drag_and_drop(", "page.set_checked(",
    "row.click(", "row.fill(", "row.check(",
    "element.click(", "element.fill(",
    ".evaluate(\"document.", "page.evaluate(",
]

GITHUB_SCRAPER_ALLOWED_PUBLIC = {
    "search_epics", "search_cards", "get_project_items", "close",
}

GITHUB_API_CLIENT_ALLOWED_PUBLIC = {
    "search_epics", "search_cards", "get_project_items", "close",
}

MONDAY_CLIENT_ALLOWED_PUBLIC = {
    "get_boards", "get_items", "get_updates", "search_items",
}


class TestGitHubScraperHasNoMutationCapability:
    def test_no_dangerous_method_names_on_scraper(self) -> None:
        from work_ai.github_client import GitHubScraper

        public_methods = {
            name for name in dir(GitHubScraper)
            if not name.startswith("_") and callable(getattr(GitHubScraper, name))
        }

        overlap = public_methods & DANGEROUS_METHOD_NAMES
        assert overlap == set(), (
            f"GitHubScraper has dangerous methods: {overlap} — "
            f"scraper must be READ ONLY"
        )

    def test_scraper_source_contains_no_mutating_playwright_calls(self) -> None:
        from work_ai.github_client import GitHubScraper

        source = inspect.getsource(GitHubScraper)

        found: list[str] = []
        for pattern in MUTATING_PLAYWRIGHT_PATTERNS:
            if pattern in source:
                found.append(pattern)

        assert found == [], (
            f"GitHubScraper source contains mutating Playwright calls: {found} — "
            f"scraper must NEVER click, fill, type, or dispatch events"
        )

    def test_scraper_only_exposes_read_methods(self) -> None:
        from work_ai.github_client import GitHubScraper

        public_methods = {
            name for name in dir(GitHubScraper)
            if not name.startswith("_") and callable(getattr(GitHubScraper, name))
        }

        unexpected = public_methods - GITHUB_SCRAPER_ALLOWED_PUBLIC
        assert unexpected == set(), (
            f"GitHubScraper has unexpected public methods: {unexpected} — "
            f"add to GITHUB_SCRAPER_ALLOWED_PUBLIC if intentional, otherwise remove"
        )

    def test_scraper_module_has_no_raw_http_imports(self) -> None:
        import work_ai.github_client as mod

        source = inspect.getsource(mod)

        forbidden = ["import requests", "from requests", "import urllib.request"]
        found = [f for f in forbidden if f in source]
        assert found == [], (
            f"github_client.py imports raw HTTP libraries: {found} — "
            f"all GitHub access must go through Playwright scraper, not HTTP"
        )

    def test_every_scraper_method_calls_gate_check(self) -> None:
        from work_ai.github_client import GitHubScraper

        source = inspect.getsource(GitHubScraper)
        read_methods = {"search_epics", "search_cards", "get_project_items"}

        for method_name in read_methods:
            method_source = inspect.getsource(getattr(GitHubScraper, method_name))
            assert "_gate.check(" in method_source or "self._gate.check(" in method_source, (
                f"GitHubScraper.{method_name} does NOT call self._gate.check() — "
                f"every public method must pass through the safety gate"
            )


class TestGitHubAPIClientHasNoMutationCapability:
    def test_no_dangerous_method_names_on_api_client(self) -> None:
        from work_ai.github_api_client import GitHubAPIClient

        public_methods = {
            name for name in dir(GitHubAPIClient)
            if not name.startswith("_") and callable(getattr(GitHubAPIClient, name))
        }

        overlap = public_methods & DANGEROUS_METHOD_NAMES
        assert overlap == set(), (
            f"GitHubAPIClient has dangerous methods: {overlap} — "
            f"API client must be READ ONLY"
        )

    def test_api_client_only_exposes_read_methods(self) -> None:
        from work_ai.github_api_client import GitHubAPIClient

        public_methods = {
            name for name in dir(GitHubAPIClient)
            if not name.startswith("_") and callable(getattr(GitHubAPIClient, name))
        }

        unexpected = public_methods - GITHUB_API_CLIENT_ALLOWED_PUBLIC
        assert unexpected == set(), (
            f"GitHubAPIClient has unexpected public methods: {unexpected} — "
            f"add to GITHUB_API_CLIENT_ALLOWED_PUBLIC if intentional, otherwise remove"
        )

    def test_every_api_client_method_calls_gate_check(self) -> None:
        from work_ai.github_api_client import GitHubAPIClient

        read_methods = {"search_epics", "search_cards", "get_project_items"}

        for method_name in read_methods:
            method_source = inspect.getsource(getattr(GitHubAPIClient, method_name))
            assert "_gate.check(" in method_source or "self._gate.check(" in method_source, (
                f"GitHubAPIClient.{method_name} does NOT call self._gate.check() — "
                f"every public method must pass through the safety gate"
            )

    def test_api_client_uses_only_get_requests(self) -> None:
        from work_ai.github_api_client import GitHubAPIClient

        source = inspect.getsource(GitHubAPIClient)

        forbidden = ["client.post(", "client.put(", "client.delete(", "client.patch("]
        found = [f for f in forbidden if f in source]
        graphql_ok = all("_GRAPHQL_URL" in source for _ in [1])
        found_non_graphql = []
        for f in found:
            if f == "client.post(" and "graphql" in source.lower():
                continue
            found_non_graphql.append(f)
        assert found_non_graphql == [], (
            f"GitHubAPIClient uses mutating HTTP methods: {found_non_graphql} — "
            f"only GET (and POST for GraphQL reads) are permitted"
        )


class TestMondayClientHasNoMutationCapability:
    def test_no_dangerous_method_names_on_monday(self) -> None:
        from work_ai.monday_client import MondayClient

        public_methods = {
            name for name in dir(MondayClient)
            if not name.startswith("_") and callable(getattr(MondayClient, name))
        }

        overlap = public_methods & DANGEROUS_MONDAY_METHOD_NAMES
        assert overlap == set(), (
            f"MondayClient has dangerous methods: {overlap} — "
            f"Monday.com must be PERMANENTLY READ ONLY"
        )

    def test_monday_only_exposes_read_methods(self) -> None:
        from work_ai.monday_client import MondayClient

        public_methods = {
            name for name in dir(MondayClient)
            if not name.startswith("_") and callable(getattr(MondayClient, name))
        }

        unexpected = public_methods - MONDAY_CLIENT_ALLOWED_PUBLIC
        assert unexpected == set(), (
            f"MondayClient has unexpected public methods: {unexpected} — "
            f"add to MONDAY_CLIENT_ALLOWED_PUBLIC if intentional, otherwise remove"
        )

    def test_monday_source_contains_no_mutation_graphql(self) -> None:
        from work_ai.monday_client import MondayClient

        source = inspect.getsource(MondayClient)
        mutation_patterns = [
            "mutation", "create_item", "change_column_value",
            "archive_board", "delete_item", "move_item_to_group",
            "duplicate_board", "create_update",
        ]

        found = [p for p in mutation_patterns if p in source]
        assert found == [], (
            f"MondayClient source contains mutation-related strings: {found} — "
            f"Monday.com must be PERMANENTLY READ ONLY"
        )

    def test_monday_token_not_exposed_via_public_attributes(self) -> None:
        from work_ai.monday_client import MondayClient

        public_attrs = {
            name for name in dir(MondayClient)
            if not name.startswith("_")
        }

        token_attrs = {
            "api_token", "token", "api_key", "key", "secret",
            "headers", "auth_header", "authorization",
        }
        overlap = public_attrs & token_attrs
        assert overlap == set(), (
            f"MondayClient exposes token-related attributes: {overlap} — "
            f"API token must stay private"
        )

    def test_every_monday_method_calls_gate_check(self) -> None:
        from work_ai.monday_client import MondayClient

        read_methods = {"get_boards", "get_items", "get_updates", "search_items"}

        for method_name in read_methods:
            method_source = inspect.getsource(getattr(MondayClient, method_name))
            assert "_gate.check(" in method_source or "self._gate.check(" in method_source, (
                f"MondayClient.{method_name} does NOT call self._gate.check() — "
                f"every public method must pass through the safety gate"
            )

    def test_monday_query_method_is_private(self) -> None:
        from work_ai.monday_client import MondayClient

        assert hasattr(MondayClient, "_query"), (
            "MondayClient._query should exist as a private method"
        )

        public_methods = {
            name for name in dir(MondayClient)
            if not name.startswith("_") and callable(getattr(MondayClient, name))
        }
        assert "query" not in public_methods, (
            "MondayClient must NOT expose a public 'query' method — "
            "generic query access would bypass safety"
        )


class TestAllowlistClientSync:
    def test_every_github_allowlist_op_maps_to_api_client_method(self) -> None:
        from work_ai.github_api_client import GitHubAPIClient

        github_ops = {
            op for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if svc == Service.GITHUB
        }

        source = inspect.getsource(GitHubAPIClient)
        for op in github_ops:
            assert f'operation="{op}"' in source, (
                f"Allowlist has GitHub operation '{op}' but GitHubAPIClient "
                f"never calls gate.check(operation=\"{op}\") — orphaned allowlist entry"
            )

    def test_every_github_allowlist_op_maps_to_scraper_method(self) -> None:
        from work_ai.github_client import GitHubScraper

        github_ops = {
            op for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if svc == Service.GITHUB
        }

        source = inspect.getsource(GitHubScraper)
        for op in github_ops:
            assert f'operation="{op}"' in source, (
                f"Allowlist has GitHub operation '{op}' but GitHubScraper "
                f"never calls gate.check(operation=\"{op}\") — orphaned allowlist entry"
            )

    def test_every_monday_allowlist_op_maps_to_client_method(self) -> None:
        from work_ai.monday_client import MondayClient

        monday_ops = {
            op for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if svc == Service.MONDAY
        }

        source = inspect.getsource(MondayClient)
        for op in monday_ops:
            assert f'operation="{op}"' in source, (
                f"Allowlist has Monday operation '{op}' but MondayClient "
                f"never calls gate.check(operation=\"{op}\") — orphaned allowlist entry"
            )


class TestRoutesAreGetOnly:
    def test_no_post_put_delete_patch_routes(self) -> None:
        from work_ai.routes import router

        for route in router.routes:
            methods = getattr(route, "methods", set())
            dangerous = methods & {"POST", "PUT", "DELETE", "PATCH"}
            path = getattr(route, "path", "unknown")
            assert dangerous == set(), (
                f"Route {path} uses HTTP methods {dangerous} — "
                f"Day Job routes must be GET-only (reads only). "
                f"Gated writes go through a separate confirmation flow."
            )

    def test_routes_only_call_read_methods(self) -> None:
        import ast
        from work_ai import routes as routes_mod

        source = inspect.getsource(routes_mod)
        tree = ast.parse(source)

        write_patterns = {
            "create_item", "update_item", "delete_item",
            "create_issue", "close_issue", "delete_issue", "update_issue",
            "set_item_iteration", "reassign", "add_label",
            "send_message", "fill_timesheet", "submit_timesheet", "upload_ppt",
        }

        found: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in write_patterns:
                found.append(node.attr)
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in write_patterns:
                    found.append(func.attr)

        assert found == [], (
            f"routes.py calls write operations: {found} — "
            f"routes must only call read methods"
        )


class TestConfirmationSignerSecurity:
    def test_short_secret_rejected(self) -> None:
        with pytest.raises(ValueError, match=">="):
            ConfirmationSigner(b"too-short")

    def test_empty_secret_rejected(self) -> None:
        with pytest.raises(ValueError, match=">="):
            ConfirmationSigner(b"")

    def test_tampered_payload_rejected(self, signer: ConfirmationSigner) -> None:
        token = signer.mint(
            service=Service.SLACK,
            operation="send_message",
            params_hash="abc123",
            now=_NOW,
        )
        payload, sig = token.rsplit("|", 1)
        tampered = payload.replace("send_message", "delete_message")

        with pytest.raises(InvalidConfirmationError):
            signer.verify(
                f"{tampered}|{sig}",
                service=Service.SLACK,
                operation="delete_message",
                params_hash="abc123",
                now=_NOW,
            )

    def test_different_secret_cannot_verify(self) -> None:
        original = ConfirmationSigner(_SECRET)
        token = original.mint(
            service=Service.SLACK,
            operation="send_message",
            params_hash="abc123",
            now=_NOW,
        )
        other_signer = ConfirmationSigner(b"different-secret-32-bytes-long!!")

        with pytest.raises(InvalidConfirmationError):
            other_signer.verify(
                token,
                service=Service.SLACK,
                operation="send_message",
                params_hash="abc123",
                now=_NOW,
            )

    def test_token_without_pipe_separator_rejected(
        self, signer: ConfirmationSigner,
    ) -> None:
        with pytest.raises(InvalidConfirmationError, match="malformed"):
            signer.verify(
                "no-pipe-in-this-token",
                service=Service.SLACK,
                operation="send_message",
                params_hash="abc123",
                now=_NOW,
            )

    def test_token_with_garbage_payload_rejected(
        self, signer: ConfirmationSigner,
    ) -> None:
        with pytest.raises(InvalidConfirmationError):
            signer.verify(
                "not-json|fakesig",
                service=Service.SLACK,
                operation="send_message",
                params_hash="abc123",
                now=_NOW,
            )

    def test_params_hash_is_deterministic(self) -> None:
        params = {"b": "2", "a": "1"}
        h1 = hash_params(params)
        h2 = hash_params(params)
        assert h1 == h2

    def test_different_params_produce_different_hashes(self) -> None:
        h1 = hash_params({"action": "delete"})
        h2 = hash_params({"action": "read"})
        assert h1 != h2

    def test_param_order_does_not_affect_hash(self) -> None:
        h1 = hash_params({"a": "1", "b": "2"})
        h2 = hash_params({"b": "2", "a": "1"})
        assert h1 == h2


class TestNoExplicitlyBlockedTierInAllowlist:
    def test_no_blocked_tier_entries_in_allowlist(self) -> None:
        blocked_entries = {
            (svc.value, op)
            for (svc, op), tier in OPERATION_ALLOWLIST.items()
            if tier == Tier.BLOCKED
        }
        assert blocked_entries == set(), (
            f"BLOCKED entries found in allowlist: {blocked_entries} — "
            f"if an operation should be blocked, remove it from the allowlist entirely"
        )


# ── LLM Handler Tests ────────────────────────────────────────────────
from work_ai.llm_handler import (
    DayJobQuery,
    SQUAD_LABELS,
    _build_label_filter,
    _detect_planning,
    _detect_squad,
    _group_by_squad,
    build_context,
    build_panel,
    parse_query,
)


class TestParseQueryIntentDetection:
    """parse_query extracts the right service, action, repo, and search term."""

    @pytest.mark.parametrize("query,expected_action", [
        ("show me the epics", "epics"),
        ("what are the current epics?", "epics"),
        ("list all epic items", "epics"),
        ("show sprint board", "sprint"),
        ("what's in the current sprint?", "sprint"),
        ("backlog items", "sprint"),
        ("show iteration", "sprint"),
        ("find the LAR ticket", "sprint"),
        ("search for auth bug", "search"),
        ("what's the status of card 42", "search"),
        ("look up the login issue", "search"),
    ])
    def test_github_action_detection(self, query: str, expected_action: str) -> None:
        under_test = parse_query(query)

        assert under_test.service == "github"
        assert under_test.action == expected_action

    @pytest.mark.parametrize("query", [
        "show me the monday board",
        "what's on monday?",
    ])
    def test_monday_detection(self, query: str) -> None:
        under_test = parse_query(query)

        assert under_test.service == "monday"
        assert under_test.action == "boards"

    def test_repo_extraction_lakitu(self) -> None:
        under_test = parse_query("show lakitu epics")

        assert under_test.repo == "lakitu"

    def test_repo_extraction_scupper(self) -> None:
        under_test = parse_query("find scupper cards")

        assert under_test.repo == "scupper"

    def test_default_repo_when_none_mentioned(self) -> None:
        under_test = parse_query("show me the epics")

        assert under_test.repo == "lakitu"

    def test_custom_default_repo(self) -> None:
        under_test = parse_query("show me the epics", default_repo="other")

        assert under_test.repo == "other"

    def test_search_term_extraction(self) -> None:
        under_test = parse_query("find the LAR authentication bug")

        assert "authentication" in under_test.search_term.lower()
        assert under_test.label_filter == "app-lar"

    def test_search_term_strips_noise_words(self) -> None:
        under_test = parse_query("show me all the open issues in lakitu please")

        assert "show" not in under_test.search_term.lower()
        assert "please" not in under_test.search_term.lower()
        assert "lakitu" not in under_test.search_term.lower()

    def test_empty_search_term_for_epics(self) -> None:
        under_test = parse_query("show me all epics")

        assert under_test.action == "epics"


class TestBuildContext:
    """build_context formats data as compact LLM context strings."""

    def test_empty_items_returns_no_data_message(self) -> None:
        query = DayJobQuery(service="github", action="epics", search_term="", repo="lakitu")

        under_test = build_context([], query)

        assert "No epics data" in under_test

    def test_issue_items_include_number_and_title(self) -> None:
        items = [{"number": 42, "title": "Fix auth", "state": "open", "labels": ["bug"],
                  "assignees": ["luke"], "url": "https://github.com/org/repo/issues/42"}]
        query = DayJobQuery(service="github", action="search", search_term="auth", repo="lakitu")

        under_test = build_context(items, query)

        assert "#42" in under_test
        assert "Fix auth" in under_test
        assert "[open]" in under_test
        assert "labels=bug" in under_test
        assert "assigned=luke" in under_test

    def test_status_items_without_number(self) -> None:
        items = [{"title": "Deploy service", "status": "In Progress", "assignees": ["luke"],
                  "url": "https://example.com"}]
        query = DayJobQuery(service="github", action="sprint", search_term="", repo="lakitu")

        under_test = build_context(items, query)

        assert "Deploy service" in under_test
        assert "[In Progress]" in under_test

    def test_truncation_at_20_items(self) -> None:
        items = [{"number": i, "title": f"Item {i}", "state": "open", "url": ""}
                 for i in range(25)]
        query = DayJobQuery(service="github", action="search", search_term="", repo="lakitu")

        under_test = build_context(items, query)

        assert "... and 5 more" in under_test

    def test_header_includes_service_and_action(self) -> None:
        items = [{"name": "Board 1"}]
        query = DayJobQuery(service="monday", action="boards", search_term="", repo="")

        under_test = build_context(items, query)

        assert "MONDAY" in under_test
        assert "BOARDS" in under_test


class TestBuildPanel:
    """build_panel creates frontend-renderable panel dicts."""

    def test_empty_items_returns_none(self) -> None:
        query = DayJobQuery(service="github", action="epics", search_term="", repo="lakitu")

        under_test = build_panel([], query)

        assert under_test is None

    def test_epics_panel_title(self) -> None:
        items = [{"number": 1, "title": "Epic 1", "state": "open", "labels": [], "assignees": [],
                  "url": "https://example.com"}]
        query = DayJobQuery(service="github", action="epics", search_term="", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "EPICS" in under_test["title"]
        assert "LAKITU" in under_test["title"]

    def test_sprint_panel_title(self) -> None:
        items = [{"title": "Task 1", "status": "Todo", "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert under_test["title"] == "SPRINT BOARD"

    def test_search_panel_title_includes_term(self) -> None:
        items = [{"number": 1, "title": "LAR thing", "state": "open", "labels": [], "assignees": [],
                  "url": ""}]
        query = DayJobQuery(service="github", action="search", search_term="LAR", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "LAR" in under_test["title"]

    def test_panel_has_table_with_headers(self) -> None:
        items = [{"number": 1, "title": "Item", "state": "open", "labels": ["bug"],
                  "assignees": ["luke"], "url": "https://example.com"}]
        query = DayJobQuery(service="github", action="search", search_term="test", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "headers" in under_test["table"]
        assert "rows" in under_test["table"]
        assert len(under_test["table"]["rows"]) == 1

    def test_panel_stats_include_total(self) -> None:
        items = [
            {"number": 1, "title": "A", "state": "open", "labels": [], "assignees": [], "url": ""},
            {"number": 2, "title": "B", "state": "closed", "labels": [], "assignees": [], "url": ""},
            {"number": 3, "title": "C", "state": "open", "labels": [], "assignees": [], "url": ""},
        ]
        query = DayJobQuery(service="github", action="search", search_term="", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        total_stat = under_test["stats"][0]
        assert total_stat["label"] == "Total Items"
        assert total_stat["value"] == "3"

    def test_panel_status_items_use_simplified_headers(self) -> None:
        items = [{"title": "Task", "status": "Done", "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="", repo="lakitu")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "#" not in under_test["table"]["headers"]
        assert "Title" in under_test["table"]["headers"]


class TestSquadDetection:
    """Squad A/B/C/D detection from natural language queries."""

    @pytest.mark.parametrize("query,expected_squad", [
        ("what's in the sprint for squad A", "a"),
        ("show squad B tickets", "b"),
        ("squad C sprint items", "c"),
        ("show me squad d", "d"),
    ])
    def test_detects_specific_squad(self, query: str, expected_squad: str) -> None:
        under_test = parse_query(query)

        assert under_test.squad == expected_squad
        assert under_test.label_filter == SQUAD_LABELS[expected_squad]

    def test_detects_all_squads(self) -> None:
        under_test = parse_query("show sprint for all squads")

        assert under_test.squad == "all"

    def test_no_squad_when_not_mentioned(self) -> None:
        under_test = parse_query("show me the sprint board")

        assert under_test.squad == ""
        assert "Squad" not in under_test.label_filter

    def test_squad_forces_sprint_action(self) -> None:
        under_test = parse_query("squad A tickets")

        assert under_test.action == "sprint"

    @pytest.mark.parametrize("query,expected_squad", [
        ("Squad A", "a"),
        ("SQUAD B", "b"),
        ("squad c", "c"),
    ])
    def test_case_insensitive_squad(self, query: str, expected_squad: str) -> None:
        under_test = _detect_squad(query.lower())

        assert under_test == expected_squad


class TestPlanningDetection:
    """Planning / upcoming / next sprint detection."""

    @pytest.mark.parametrize("query", [
        "what's in planning",
        "show me coming next",
        "next sprint tickets",
        "upcoming items",
        "what's planned",
        "show queued tickets",
        "ready for dev items",
    ])
    def test_detects_planning_intent(self, query: str) -> None:
        assert _detect_planning(query) is True

    def test_no_planning_for_current_sprint(self) -> None:
        assert _detect_planning("show me the current sprint") is False

    def test_planning_forces_sprint_action(self) -> None:
        under_test = parse_query("what's in planning")

        assert under_test.action == "sprint"
        assert "Planning" in under_test.label_filter

    def test_squad_plus_planning_combined(self) -> None:
        under_test = parse_query("what's coming next for squad B")

        assert under_test.squad == "b"
        assert "Squad B" in under_test.label_filter
        assert "Planning" in under_test.label_filter

    def test_all_squads_planning(self) -> None:
        under_test = parse_query("planning tickets for all squads")

        assert under_test.squad == "all"
        assert "Planning" in under_test.label_filter


class TestLabelFilterBuilding:
    """_build_label_filter produces correct comma-separated label strings."""

    def test_single_squad(self) -> None:
        assert _build_label_filter("a", False) == "Squad A"

    def test_planning_only(self) -> None:
        assert _build_label_filter("", True) == "Planning"

    def test_squad_plus_planning(self) -> None:
        under_test = _build_label_filter("c", True)

        assert "Squad C" in under_test
        assert "Planning" in under_test

    def test_all_squads_no_squad_label(self) -> None:
        under_test = _build_label_filter("all", False)

        assert under_test == ""

    def test_all_squads_with_planning(self) -> None:
        under_test = _build_label_filter("all", True)

        assert under_test == "Planning"

    def test_no_filters(self) -> None:
        assert _build_label_filter("", False) == ""


class TestGroupBySquad:
    """_group_by_squad sorts items so each squad's tickets are together."""

    def test_groups_by_squad_label(self) -> None:
        items = [
            {"title": "B1", "labels": ["Squad B"], "state": "open"},
            {"title": "A1", "labels": ["Squad A"], "state": "open"},
            {"title": "A2", "labels": ["Squad A"], "state": "open"},
            {"title": "C1", "labels": ["Squad C"], "state": "open"},
        ]

        under_test = _group_by_squad(items)

        titles = [i["title"] for i in under_test]
        assert titles == ["A1", "A2", "B1", "C1"]

    def test_items_without_squad_go_last(self) -> None:
        items = [
            {"title": "No Squad", "labels": ["bug"], "state": "open"},
            {"title": "A1", "labels": ["Squad A"], "state": "open"},
        ]

        under_test = _group_by_squad(items)

        assert under_test[0]["title"] == "A1"
        assert under_test[1]["title"] == "No Squad"


class TestSquadPanelTitles:
    """Panel titles reflect squad and planning filters."""

    def test_squad_a_panel_title(self) -> None:
        items = [{"number": 1, "title": "T", "state": "open", "labels": ["Squad A"],
                  "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="",
                            repo="lakitu", squad="a", label_filter="Squad A")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "SQUAD A" in under_test["title"]

    def test_planning_panel_title(self) -> None:
        items = [{"number": 1, "title": "T", "state": "open", "labels": ["Planning"],
                  "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="",
                            repo="lakitu", squad="", label_filter="Planning")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "PLANNING" in under_test["title"]

    def test_squad_b_planning_panel_title(self) -> None:
        items = [{"number": 1, "title": "T", "state": "open", "labels": [],
                  "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="",
                            repo="lakitu", squad="b", label_filter="Squad B,Planning")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "SQUAD B" in under_test["title"]
        assert "PLANNING" in under_test["title"]

    def test_all_squads_panel_title(self) -> None:
        items = [{"number": 1, "title": "T", "state": "open", "labels": [],
                  "assignees": [], "url": ""}]
        query = DayJobQuery(service="github", action="sprint", search_term="",
                            repo="lakitu", squad="all", label_filter="")

        under_test = build_panel(items, query)

        assert under_test is not None
        assert "ALL SQUADS" in under_test["title"]
