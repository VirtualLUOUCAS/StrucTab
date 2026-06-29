"""
Server endpoint registry for the four reward dependencies.

Each dependency is backed by one JSON file under ``Uni_TabRL/configs/servers``.
The JSON content is simply a list of ``"host:port"`` strings, e.g.::

    ["10.0.0.1:8000", "10.0.0.2:8000"]

so that the reward clients can load these endpoints and round-robin over them.
The four dependencies are:

    - hunyuan_ocr  : HunyuanOCR served as the Anchor OCR model
    - html_render  : the HTML-to-image rendering engine
    - teds_judger  : the TEDS / TEDS-S scoring service
    - vlm_judge    : the VLM-as-judge consistency service
"""

import json
import os

# configs/servers lives at: <repo>/Uni_TabRL/configs/servers
_SERVERS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "configs",
    "servers",
)


def _load(filename: str) -> list[str]:
    path = os.path.join(_SERVERS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_hunyuan_ocr_servers() -> list[str]:
    """Endpoints of the HunyuanOCR (Anchor OCR) service."""
    return _load("hunyuan_ocr.json")


def get_html_render_servers() -> list[str]:
    """Endpoints of the HTML rendering service."""
    return _load("html_render.json")


def get_teds_judger_servers() -> list[str]:
    """Endpoints of the TEDS / TEDS-S scoring service."""
    return _load("teds_judger.json")


def get_vlm_judge_servers() -> list[str]:
    """Endpoints of the VLM-as-judge service."""
    return _load("vlm_judge.json")
