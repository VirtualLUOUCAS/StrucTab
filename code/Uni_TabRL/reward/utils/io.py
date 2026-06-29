"""Lightweight IO helpers used by the reward clients."""

import base64

import requests


def encode_image(image_path: str) -> str:
    """Read an image (local path or http(s) URL) and return its base64 string."""
    if image_path.startswith("http"):
        content = requests.get(image_path, timeout=30).content
        return base64.b64encode(content).decode("utf-8")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
