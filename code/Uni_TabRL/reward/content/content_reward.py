"""
Content reward (R_content) of Uni-TabRL.

Three variants are supported:

    - ``teds``      : raw TEDS between the prediction and the reference (baseline).
    - ``vlm_judge`` : a VLM-as-judge inspects a side-by-side rendering of the two
                      tables and returns a binary visual-consistency verdict.
    - ``anchor``    : the proposed Anchor-Guided Destylization. Both the
                      prediction and the reference are rendered into standardized
                      images and re-parsed by a frozen Anchor OCR model
                      (HunyuanOCR); TEDS is then computed on these de-stylized
                      representations so the reward focuses on semantic content
                      rather than stylistic differences.
"""

import os

from .prompts import VLM_JUDGE_SYSTEM_PROMPT, VLM_JUDGE_USER_PROMPT
from .utils import (
    RENDER_IMAGE_DIR,
    anchor_ocr_client,
    gen_image_name,
    parse_vlm_verdict,
    render_client,
    teds_client,
    vlm_judge_client,
)


def teds_content_reward(pred_table: str, ref_table: str) -> float:
    """Baseline content reward: raw TEDS between prediction and reference."""
    result = teds_client.call(pred_table, ref_table)
    return result.get("teds")


def vlm_judge_content_reward(pred_table: str, ref_table: str) -> dict:
    """
    VLM-as-judge content reward.

    Renders the prediction and reference side by side, asks the VLM judge whether
    they are visually consistent, and maps the verdict to a binary score.
    """
    image_name = gen_image_name(pred_table, ref_table)
    render_result = render_client.render_dual(
        content_left=pred_table,
        content_right=ref_table,
        image_name=image_name,
        output_dir=RENDER_IMAGE_DIR,
    )
    image_path = render_result.get("image_path")
    if not image_path or not os.path.exists(image_path):
        return {
            "score": 0.0,
            "decision": "false",
            "reason": "Rendered image not found.",
            "render_image": image_path,
        }

    resp = vlm_judge_client.call(
        image_path=image_path,
        question=VLM_JUDGE_USER_PROMPT,
        system_prompt=VLM_JUDGE_SYSTEM_PROMPT,
    )
    verdict = parse_vlm_verdict(resp.get("output") or "")
    verdict["render_image"] = image_path
    return verdict


def anchor_destylization_content_reward(pred_table: str, ref_table_destylized: str) -> dict | None:
    """
    Anchor-Guided Destylization content reward.

    Renders the prediction into a standardized image, re-parses it with the
    frozen Anchor OCR model, and computes TEDS against the (offline-precomputed)
    de-stylized reference. Returns ``None`` if any stage fails.
    """
    image_name = gen_image_name(pred_table)
    render_result = render_client.render_single(
        content=pred_table,
        image_name=image_name,
        output_dir=RENDER_IMAGE_DIR,
    )
    image_path = render_result.get("image_path")
    if not image_path or not os.path.exists(image_path):
        return None

    ocr_resp = anchor_ocr_client.call(image_path=image_path)
    parsed = ocr_resp.get("output")
    if not parsed or not parsed.strip():
        return None

    score_result = teds_client.call(parsed, ref_table_destylized)
    return {
        "parsing_result": parsed,
        "teds": score_result.get("teds"),
        "teds_s": score_result.get("teds_s"),
        "render_image": image_path,
    }
