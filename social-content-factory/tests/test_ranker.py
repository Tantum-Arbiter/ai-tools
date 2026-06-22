from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import respx

from social_content_factory.brand_loader import load_brand
from social_content_factory.ingest.github_releases import RawIngestItem
from social_content_factory.ingest.ranker import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OllamaRankerClient,
    RankedCandidate,
    RankerClient,
    RankerError,
    make_ranker_client,
    rank_items,
)
from social_content_factory.schemas.brand import Brand

MODULE_ROOT = pytest.importorskip("pathlib").Path(__file__).parent.parent
BRANDS_DIR = MODULE_ROOT / "brands"


def _ollama_message(payload: dict[str, Any]) -> dict[str, Any]:
    return {"message": {"content": json.dumps(payload)}}


def _good_payload(slug: str = "phase-4-ship", score: float = 0.82) -> dict[str, Any]:
    return {
        "score": score,
        "slug": slug,
        "title": "Shipped Phase 4",
        "subject": "a glowing terminal beside a calm desk",
        "narrative": "instagram publish hook done, dry-run by default",
        "tags": ["build", "ship"],
    }


def _item() -> RawIngestItem:
    return RawIngestItem(
        source="github",
        tag="v0.4",
        title="Phase 4 publish hook",
        body="Adds factory publish command.",
        url="https://github.com/owner/repo/releases/tag/v0.4",
        published_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
    )


def _client() -> OllamaRankerClient:
    return OllamaRankerClient(base_url="http://localhost:11434", model="phi4:14b")


class TestOllamaRankerClientInit:
    def test_from_env_uses_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCF_OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("SCF_RANKER_MODEL", raising=False)

        under_test = OllamaRankerClient.from_env()

        assert under_test.base_url == DEFAULT_BASE_URL
        assert under_test.model == DEFAULT_MODEL

    def test_from_env_reads_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_OLLAMA_BASE_URL", "http://example.local:11434")
        monkeypatch.setenv("SCF_RANKER_MODEL", "phi4:6b")

        under_test = OllamaRankerClient.from_env()

        assert under_test.base_url == "http://example.local:11434"
        assert under_test.model == "phi4:6b"


class TestRankOne:
    @respx.mock
    async def test_returns_ranked_candidate(self) -> None:
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=_ollama_message(_good_payload()))
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        result = await _client().rank(brand, _item())

        assert isinstance(result, RankedCandidate)
        assert result.score == pytest.approx(0.82)
        assert result.slug == "phase-4-ship"
        assert result.title == "Shipped Phase 4"
        assert result.source_url == _item().url
        assert result.source == "github"

    @respx.mock
    async def test_score_clamped_to_unit_interval(self) -> None:
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(
                200, json=_ollama_message(_good_payload(score=1.5))
            )
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        result = await _client().rank(brand, _item())

        assert result.score == 1.0

    @respx.mock
    async def test_negative_score_clamped_to_zero(self) -> None:
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(
                200, json=_ollama_message(_good_payload(score=-0.3))
            )
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        result = await _client().rank(brand, _item())

        assert result.score == 0.0

    @respx.mock
    async def test_missing_slug_raises(self) -> None:
        payload = _good_payload()
        payload.pop("slug")
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=_ollama_message(payload))
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        with pytest.raises(RankerError):
            await _client().rank(brand, _item())

    @respx.mock
    async def test_non_json_content_raises(self) -> None:
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(
                200, json={"message": {"content": "not json at all"}}
            )
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        with pytest.raises(RankerError):
            await _client().rank(brand, _item())

    @respx.mock
    async def test_http_error_raises(self) -> None:
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(500, text="boom")
        )
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        with pytest.raises(RankerError):
            await _client().rank(brand, _item())


class TestRankItems:
    async def test_filters_below_min_score(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        brand = load_brand("personal", brands_dir=BRANDS_DIR)
        items = [_item(), RawIngestItem(**{**_item().__dict__, "tag": "v0.3"})]

        async def fake_rank(self, brand_arg, item_arg):
            score = 0.9 if item_arg.tag == "v0.4" else 0.2
            return RankedCandidate(
                score=score,
                slug=f"slug-{item_arg.tag}",
                title="t", subject="s", narrative="n", tags=["x"],
                source="github", source_url=item_arg.url,
                ingested_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
            )

        monkeypatch.setattr(OllamaRankerClient, "rank", fake_rank)

        results = await rank_items(_client(), brand, items, min_score=0.5)

        assert [r.slug for r in results] == ["slug-v0.4"]

    async def test_sorts_by_score_descending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        brand = load_brand("personal", brands_dir=BRANDS_DIR)
        items = [_item(), RawIngestItem(**{**_item().__dict__, "tag": "v0.3"})]
        scores = iter([0.4, 0.9])

        async def fake_rank(self, brand_arg, item_arg):
            score = next(scores)
            return RankedCandidate(
                score=score,
                slug=f"slug-{item_arg.tag}",
                title="t", subject="s", narrative="n", tags=["x"],
                source="github", source_url=item_arg.url,
                ingested_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
            )

        monkeypatch.setattr(OllamaRankerClient, "rank", fake_rank)

        results = await rank_items(_client(), brand, items, min_score=0.0)

        assert [r.score for r in results] == [0.9, 0.4]


def _openrouter_brand() -> Brand:
    return Brand(
        key="router",
        name="Router",
        voice="calm",
        audience="builders",
        visual_style="dark",
        negative_prompts=["nsfw"],
        default_formats=["1x1"],
        llm_provider="openrouter",
        llm_model="anthropic/claude-sonnet-4-5",
    )


class TestMakeRankerClient:
    @respx.mock
    async def test_uses_openrouter_when_brand_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(_good_payload())}}
                    ]
                },
            )
        )

        under_test = make_ranker_client(_openrouter_brand())
        result = await under_test.rank(_openrouter_brand(), _item())

        assert isinstance(result, RankedCandidate)
        assert result.model == "anthropic/claude-sonnet-4-5"
        assert route.called

    def test_phi4_brand_returns_ranker_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        brand = load_brand("personal", brands_dir=BRANDS_DIR)

        under_test = make_ranker_client(brand)

        assert isinstance(under_test, RankerClient)
        assert under_test.model == "phi4:14b"
