from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL: Final[str] = "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 300.0
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 1.0
HEALTH_TIMEOUT_SECONDS: Final[float] = 30.0


class ComfyUIError(Exception):
    """Base error for the ComfyUI client."""


class ComfyUIConfigError(ComfyUIError):
    """Raised when client configuration is missing or invalid."""


class ComfyUISubmitError(ComfyUIError):
    """Raised when ComfyUI rejects a workflow submission."""


class ComfyUIExecutionError(ComfyUIError):
    """Raised when ComfyUI reports a workflow execution error."""


class ComfyUITimeoutError(ComfyUIError):
    """Raised when a workflow does not complete within the allotted time."""


@dataclass(frozen=True)
class RenderedImage:
    image_bytes: bytes
    filename: str
    subfolder: str
    prompt_id: str


class ComfyUIClient:
    def __init__(self, *, base_url: str, model: str, client_id: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client_id = client_id or str(uuid.uuid4())

    @classmethod
    def from_env(cls) -> "ComfyUIClient":
        base_url = os.environ.get("SCF_COMFYUI_BASE_URL")
        if not base_url:
            raise ComfyUIConfigError(
                "SCF_COMFYUI_BASE_URL is not set; export it to point at the Windows ComfyUI host"
            )
        return cls(base_url=base_url, model=os.environ.get("SCF_COMFYUI_MODEL", DEFAULT_MODEL))

    async def health_check(self, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.warning("comfyui health_check failed: %s", exc)
            return False

    async def submit(self, workflow: dict) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/prompt", json=payload)
        if response.status_code != 200:
            raise ComfyUISubmitError(
                f"comfyui rejected workflow: HTTP {response.status_code} {response.text}"
            )
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise ComfyUISubmitError("comfyui returned no prompt_id")
        logger.info("comfyui submitted prompt_id=%s", prompt_id)
        return prompt_id

    async def wait_for_completion(
        self,
        prompt_id: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> dict:
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                entry = response.json().get(prompt_id) if response.status_code == 200 else None
                if entry:
                    status_str = entry.get("status", {}).get("status_str", "")
                    if status_str == "error":
                        raise ComfyUIExecutionError(_extract_error_message(entry))
                    if entry.get("outputs"):
                        return entry
                if time.monotonic() >= deadline:
                    raise ComfyUITimeoutError(
                        f"comfyui prompt {prompt_id} did not complete within {timeout}s"
                    )
                await asyncio.sleep(poll_interval)

    async def fetch_image(
        self, filename: str, subfolder: str = "", folder_type: str = "output"
    ) -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/view", params=params)
        if response.status_code != 200:
            raise ComfyUIError(f"comfyui /view returned HTTP {response.status_code}")
        return response.content

    async def render(
        self,
        workflow: dict,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> RenderedImage:
        prompt_id = await self.submit(workflow)
        history = await self.wait_for_completion(prompt_id, timeout=timeout, poll_interval=poll_interval)
        image_info = _first_image(history)
        image_bytes = await self.fetch_image(
            image_info["filename"],
            subfolder=image_info.get("subfolder", ""),
            folder_type=image_info.get("type", "output"),
        )
        return RenderedImage(
            image_bytes=image_bytes,
            filename=image_info["filename"],
            subfolder=image_info.get("subfolder", ""),
            prompt_id=prompt_id,
        )


def _first_image(history_entry: dict) -> dict:
    for node_output in history_entry.get("outputs", {}).values():
        images = node_output.get("images") or []
        if images:
            return images[0]
    raise ComfyUIExecutionError("comfyui history contained no images")


def _extract_error_message(history_entry: dict) -> str:
    for message in history_entry.get("status", {}).get("messages", []):
        if isinstance(message, list) and len(message) >= 2 and message[0] == "execution_error":
            payload = message[1]
            if isinstance(payload, dict):
                return str(payload.get("exception_message", "comfyui execution error"))
    return "comfyui execution error"
