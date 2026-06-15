"""
ComfyUI API Client
Submits image generation jobs to ComfyUI running locally on the Windows RTX 3080.
ComfyUI API docs: https://github.com/comfyanonymous/ComfyUI/blob/master/server.py
"""
import os
import json
import time
import uuid
import logging
import shutil
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# Brand-consistent style suffix appended to every image prompt
BRAND_STYLE_SUFFIX = (
    "warm golden hour lighting, soft bokeh background, calm cozy home environment, "
    "photorealistic, cinematic, warm colour palette, sage green and terracotta tones, "
    "8k, highly detailed, professional photography"
)

BRAND_NEGATIVE = (
    "cartoon, anime, bright primary colours, clutter, ugly, deformed, blurry, "
    "child face, children's faces visible, dark, horror, violence, nsfw, "
    "text overlay, watermark, logo"
)

# Base ComfyUI API workflow for image generation (SDXL / Flux compatible)
BASE_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "seed": 0,        # Overridden per request
            "steps": 30,
        },
    },
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},  # Set from env
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 1024, "width": 1024},
    },
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "gwf_", "images": ["8", 0]},
    },
}


class ComfyUIClient:
    def __init__(self, base_url: str = "http://localhost:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.output_dir = Path(os.getenv("COMFYUI_OUTPUT_DIR", "data/content/raw"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = os.getenv("COMFYUI_CHECKPOINT", "dreamshaper_8.safetensors")

    def health_check(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/system_stats", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1080,
        steps: int = 30,
        seed: int | None = None,
    ) -> Path:
        """Submit a generation job and wait for completion. Returns local file path."""
        if not self.health_check():
            raise ConnectionError(f"ComfyUI not reachable at {self.base_url}. Is it running?")

        full_prompt = f"{prompt}, {BRAND_STYLE_SUFFIX}"
        full_negative = f"{negative_prompt}, {BRAND_NEGATIVE}" if negative_prompt else BRAND_NEGATIVE

        workflow = self._build_workflow(
            positive=full_prompt,
            negative=full_negative,
            width=width,
            height=height,
            steps=steps,
            seed=seed or int(time.time()),
        )

        log.info(f"Submitting ComfyUI job: {width}x{height}")
        prompt_id = self._submit(workflow)
        log.info(f"Job submitted: {prompt_id}. Waiting...")

        output_file = self._wait_for_output(prompt_id)
        log.info(f"ComfyUI generation complete: {output_file}")
        return output_file

    def _build_workflow(self, positive, negative, width, height, steps, seed) -> dict:
        import copy
        wf = copy.deepcopy(BASE_WORKFLOW)
        wf["4"]["inputs"]["ckpt_name"] = self.checkpoint
        wf["5"]["inputs"]["width"] = width
        wf["5"]["inputs"]["height"] = height
        wf["3"]["inputs"]["steps"] = steps
        wf["3"]["inputs"]["seed"] = seed
        wf["6"]["inputs"]["text"] = positive
        wf["7"]["inputs"]["text"] = negative
        return wf

    def _submit(self, workflow: dict) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        r = httpx.post(f"{self.base_url}/prompt", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["prompt_id"]

    def _wait_for_output(self, prompt_id: str, timeout: int = 300) -> Path:
        """Poll ComfyUI history until job completes, then copy output to local dir."""
        start = time.time()
        while time.time() - start < timeout:
            r = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
            data = r.json()
            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    for img in node_output.get("images", []):
                        # Download from ComfyUI output folder
                        src = Path(os.getenv("COMFYUI_OUTPUT_DIR", "")) / img["filename"]
                        if not src.exists():
                            # Try fetching via API
                            return self._download_image(img["filename"], img.get("subfolder", ""))
                        dest = self.output_dir / img["filename"]
                        shutil.copy2(src, dest)
                        return dest
            time.sleep(2)
        raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout}s")

    def _download_image(self, filename: str, subfolder: str = "") -> Path:
        params = {"filename": filename, "subfolder": subfolder, "type": "output"}
        r = httpx.get(f"{self.base_url}/view", params=params, timeout=30)
        r.raise_for_status()
        dest = self.output_dir / filename
        dest.write_bytes(r.content)
        return dest
