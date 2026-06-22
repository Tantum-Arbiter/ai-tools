from __future__ import annotations

import httpx
import pytest
import respx

from social_content_factory.comfyui_client import (
    ComfyUIClient,
    ComfyUIConfigError,
    ComfyUIExecutionError,
    ComfyUISubmitError,
    ComfyUITimeoutError,
    RenderedImage,
)

BASE_URL = "http://192.168.1.213:8188"
MODEL = "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors"


def _client() -> ComfyUIClient:
    return ComfyUIClient(base_url=BASE_URL, model=MODEL)


def _history_complete(prompt_id: str) -> dict:
    return {
        prompt_id: {
            "outputs": {
                "8": {
                    "images": [
                        {"filename": "scf_00001_.png", "subfolder": "", "type": "output"}
                    ]
                }
            },
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }


def _history_error(prompt_id: str) -> dict:
    return {
        prompt_id: {
            "outputs": {},
            "status": {
                "status_str": "error",
                "completed": False,
                "messages": [["execution_error", {"exception_message": "OOM"}]],
            },
        }
    }


class TestFromEnv:
    def test_uses_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_COMFYUI_BASE_URL", BASE_URL)
        monkeypatch.setenv("SCF_COMFYUI_MODEL", "custom_model.safetensors")

        under_test = ComfyUIClient.from_env()

        assert under_test.base_url == BASE_URL
        assert under_test.model == "custom_model.safetensors"

    def test_missing_base_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCF_COMFYUI_BASE_URL", raising=False)
        with pytest.raises(ComfyUIConfigError, match="SCF_COMFYUI_BASE_URL"):
            ComfyUIClient.from_env()

    def test_model_defaults_to_sd35(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_COMFYUI_BASE_URL", BASE_URL)
        monkeypatch.delenv("SCF_COMFYUI_MODEL", raising=False)

        under_test = ComfyUIClient.from_env()

        assert under_test.model == MODEL


class TestHealthCheck:
    @respx.mock
    async def test_returns_true_on_200(self) -> None:
        respx.get(f"{BASE_URL}/system_stats").mock(return_value=httpx.Response(200, json={}))
        assert await _client().health_check() is True

    @respx.mock
    async def test_returns_false_on_500(self) -> None:
        respx.get(f"{BASE_URL}/system_stats").mock(return_value=httpx.Response(500))
        assert await _client().health_check() is False

    @respx.mock
    async def test_returns_false_on_connection_error(self) -> None:
        respx.get(f"{BASE_URL}/system_stats").mock(side_effect=httpx.ConnectError("nope"))
        assert await _client().health_check() is False


class TestSubmit:
    @respx.mock
    async def test_returns_prompt_id(self) -> None:
        respx.post(f"{BASE_URL}/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )

        result = await _client().submit({"1": {"class_type": "KSampler", "inputs": {}}})

        assert result == "abc-123"

    @respx.mock
    async def test_sends_workflow_and_client_id(self) -> None:
        route = respx.post(f"{BASE_URL}/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )
        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}

        await _client().submit(workflow)

        body = route.calls.last.request.read()
        assert b'"prompt"' in body
        assert b'"client_id"' in body
        assert b'"KSampler"' in body

    @respx.mock
    async def test_raises_on_4xx_with_error_body(self) -> None:
        respx.post(f"{BASE_URL}/prompt").mock(
            return_value=httpx.Response(400, json={"error": "invalid graph"})
        )
        with pytest.raises(ComfyUISubmitError, match="400"):
            await _client().submit({})


class TestWaitForCompletion:
    @respx.mock
    async def test_returns_history_on_success(self) -> None:
        respx.get(f"{BASE_URL}/history/abc-123").mock(
            return_value=httpx.Response(200, json=_history_complete("abc-123"))
        )

        result = await _client().wait_for_completion("abc-123", poll_interval=0.01)

        assert result["status"]["status_str"] == "success"
        assert result["outputs"]["8"]["images"][0]["filename"] == "scf_00001_.png"

    @respx.mock
    async def test_polls_until_present(self) -> None:
        respx.get(f"{BASE_URL}/history/abc-123").mock(side_effect=[
            httpx.Response(200, json={}),
            httpx.Response(200, json={}),
            httpx.Response(200, json=_history_complete("abc-123")),
        ])

        result = await _client().wait_for_completion("abc-123", poll_interval=0.01)

        assert result["status"]["status_str"] == "success"

    @respx.mock
    async def test_raises_on_execution_error(self) -> None:
        respx.get(f"{BASE_URL}/history/abc-123").mock(
            return_value=httpx.Response(200, json=_history_error("abc-123"))
        )
        with pytest.raises(ComfyUIExecutionError, match="OOM"):
            await _client().wait_for_completion("abc-123", poll_interval=0.01)

    @respx.mock
    async def test_raises_on_timeout(self) -> None:
        respx.get(f"{BASE_URL}/history/abc-123").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(ComfyUITimeoutError):
            await _client().wait_for_completion("abc-123", timeout=0.05, poll_interval=0.01)


class TestFetchImage:
    @respx.mock
    async def test_returns_bytes(self) -> None:
        respx.get(f"{BASE_URL}/view").mock(
            return_value=httpx.Response(200, content=b"\x89PNG\r\n\x1a\n...")
        )

        result = await _client().fetch_image("scf_00001_.png")

        assert result.startswith(b"\x89PNG")

    @respx.mock
    async def test_passes_query_params(self) -> None:
        route = respx.get(f"{BASE_URL}/view").mock(
            return_value=httpx.Response(200, content=b"png")
        )

        await _client().fetch_image("f.png", subfolder="sub", folder_type="output")

        url = str(route.calls.last.request.url)
        assert "filename=f.png" in url
        assert "subfolder=sub" in url
        assert "type=output" in url


class TestRender:
    @respx.mock
    async def test_orchestrates_submit_wait_fetch(self) -> None:
        respx.post(f"{BASE_URL}/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )
        respx.get(f"{BASE_URL}/history/abc-123").mock(
            return_value=httpx.Response(200, json=_history_complete("abc-123"))
        )
        respx.get(f"{BASE_URL}/view").mock(
            return_value=httpx.Response(200, content=b"\x89PNGFAKE")
        )

        result = await _client().render(
            {"1": {"class_type": "KSampler", "inputs": {}}}, poll_interval=0.01
        )

        assert isinstance(result, RenderedImage)
        assert result.image_bytes == b"\x89PNGFAKE"
        assert result.filename == "scf_00001_.png"
        assert result.prompt_id == "abc-123"
