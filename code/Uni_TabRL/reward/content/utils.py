"""
Helper utilities for the content reward:

    - shared service clients (TEDS judge, renderer, anchor OCR, VLM judge);
    - the directory where intermediate rendered images are written;
    - a unique image-name generator;
    - parsing of the VLM judge's JSON verdict.
"""

import hashlib
import json
import os
from datetime import datetime

from ..utils.clients import HunyuanOcrClient, RenderClient, TedsJudgeClient, VlmJudgeClient

# Shared service clients (singletons).
teds_client: TedsJudgeClient = TedsJudgeClient()
render_client: RenderClient = RenderClient()
anchor_ocr_client: HunyuanOcrClient = HunyuanOcrClient()
vlm_judge_client: VlmJudgeClient = VlmJudgeClient()

# Directory for the rendered intermediate images, configured via env vars.
_OUTPUT_DIR = os.getenv("OUTPUT_PATH")
_PROJECT_NAME = os.getenv("PROJECT_NAME")
_EXPERIMENT_NAME = os.getenv("EXPERIMENT_NAME")
assert _OUTPUT_DIR and _PROJECT_NAME and _EXPERIMENT_NAME, (
    "Please set OUTPUT_PATH, PROJECT_NAME, and EXPERIMENT_NAME environment variables."
)
RENDER_IMAGE_DIR = os.path.join(_OUTPUT_DIR, _PROJECT_NAME, _EXPERIMENT_NAME, "render_images")
os.makedirs(RENDER_IMAGE_DIR, mode=0o777, exist_ok=True)


def gen_image_name(*parts: str, file_type: str = ".png") -> str:
    """Generate a unique image file name from a content hash and a timestamp."""
    combined = "".join(parts)
    assert combined, "Table content for image-name generation is empty."
    content_hash = hashlib.md5(combined.encode("utf-8")).hexdigest()[:16]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"table_render_{timestamp}_{content_hash}{file_type}"


def parse_vlm_verdict(raw_response: str) -> dict:
    """Extract the binary verdict from a (possibly fenced) VLM JSON response."""
    if "```json" in raw_response:
        json_str = raw_response.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_response:
        json_str = raw_response.split("```")[1].split("```")[0].strip()
    else:
        json_str = raw_response.strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        result = {"raw_resp": raw_response, "error": f"JSONDecodeError: {e}"}

    decision = str(result.get("decision", "false")).lower()
    return {
        "score": 1.0 if decision == "true" else 0.0,
        "decision": decision,
        "reason": result.get("reason", ""),
    }
