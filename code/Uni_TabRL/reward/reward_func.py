"""
Uni-TabRL reward entry point.

Computes the decomposed reward described in the paper:

    R = lambda_1 * R_validity + lambda_2 * R_structure + lambda_3 * R_content

where
    - R_validity  is a binary hard-gating signal (row-column AND merged-cell
                  analysis both exactly correct);
    - R_structure is either structure-only TEDS or the 1D Probe structural reward;
    - R_content   is either raw TEDS, a VLM-as-judge verdict, or the
                  Anchor-Guided Destylization TEDS.

If the response is not even syntactically parsable (missing section markers or an
unterminated final table), the whole reward is 0, since neither structure nor
content can be evaluated. The choice of structure / content variant is controlled
by ``config.py`` (see its docstring for the ablation mapping).
"""

import json

from . import config
from .content import anchor_destylization_content_reward, vlm_judge_content_reward
from .structure import clean_table_content, one_d_probe_reward
from .utils.clients import ClientResponse, TedsJudgeClient
from .utils.parsing import extract_sections, has_all_sections
from .validity import validity_reward

_teds_client = TedsJudgeClient()

print(f"[Uni-TabRL reward] STRUCTURE_REWARD={config.STRUCTURE_REWARD}, CONTENT_REWARD={config.CONTENT_REWARD}")


def _compute_structure_reward(pred_table: str, ref_table: str, base_teds_s: float) -> dict:
    """Return the structure reward score plus diagnostic fields."""
    if config.STRUCTURE_REWARD == "1d_probe":
        probe = one_d_probe_reward(clean_table_content(pred_table), clean_table_content(ref_table))
        return {"score": probe["score"], "one_d_probe": probe}
    # "teds_s": holistic structure-only TEDS
    return {"score": base_teds_s, "one_d_probe": None}


def _compute_content_reward(
    pred_table: str,
    ref_table: str,
    base_teds: float,
    split: str,
    ref_destylized: dict | None,
) -> dict:
    """Return the content reward score plus diagnostic fields."""
    # Content variants other than raw TEDS are only applied during training.
    if split != "train" or config.CONTENT_REWARD == "teds":
        return {"score": base_teds, "detail": None}

    if config.CONTENT_REWARD == "vlm_judge":
        verdict = vlm_judge_content_reward(pred_table, ref_table)
        return {"score": verdict["score"], "detail": {"vlm_judge": verdict}}

    if config.CONTENT_REWARD == "anchor":
        # Anchor-Guided Destylization is applied only to samples flagged for it;
        # otherwise we fall back to raw TEDS.
        if ref_destylized and ref_destylized.get("should_de_stylize"):
            anchor = anchor_destylization_content_reward(pred_table, ref_destylized["de_stylize_ref"])
            if anchor and anchor.get("teds") is not None:
                return {"score": anchor["teds"], "detail": {"anchor": anchor}}
        return {"score": base_teds, "detail": None}

    return {"score": base_teds, "detail": None}


def _build_analysis(
    final_reward: float,
    weights: tuple[float, float, float],
    r_validity: float,
    structure: dict,
    content: dict,
    base_scores: dict,
    split: str,
) -> dict:
    """Assemble a JSON-serializable diagnostic record for logging."""
    analysis = {
        "reward": round(final_reward, 5),
        "weights": list(weights),
        "components": {
            "validity": round(r_validity, 5),
            "structure": round(structure["score"], 5),
            "content": round(content["score"], 5),
        },
        "variants": {
            "structure": config.STRUCTURE_REWARD,
            "content": config.CONTENT_REWARD,
        },
        "base_metrics": {
            "teds": round(base_scores["teds"], 5),
            "teds_s": round(base_scores["teds_s"], 5),
        },
        "split": split,
    }
    if structure["one_d_probe"] is not None:
        probe = structure["one_d_probe"]
        analysis["one_d_probe"] = {
            "score": round(probe["score"], 5),
            "matched": probe["matched_cells"],
            "total": probe["total_cells"],
        }
    if content["detail"]:
        analysis["content_detail"] = content["detail"]
    return analysis


def compute_reward(
    response: str,
    ref_answer: str,
    split: str = "train",
    ref_destylized: dict | None = None,
    weights: tuple[float, float, float] | None = None,
) -> dict:
    """
    Compute the Uni-TabRL reward for a single (response, reference) pair.

    Args:
        response:      model response in the sequential-reasoning format.
        ref_answer:    reference answer in the same format.
        split:         "train" or "test"; non-TEDS content variants apply only to train.
        ref_destylized: optional dict with keys ``should_de_stylize`` (bool) and
                        ``de_stylize_ref`` (the offline de-stylized reference table),
                        used by the Anchor-Guided Destylization content reward.
        weights:       (lambda_1, lambda_2, lambda_3); defaults to the paper's values.

    Returns:
        dict with ``reward`` (float), ``is_valid`` (bool) and ``analysis`` (JSON string).
    """
    try:
        if weights is None:
            weights = (config.VALIDITY_WEIGHT, config.STRUCTURE_WEIGHT, config.CONTENT_WEIGHT)

        # --- Hard gate: response must be syntactically parsable ---
        if not has_all_sections(response):
            return {"analysis": "Response missing section markers.", "is_valid": True, "reward": 0.0}

        parsed_response = extract_sections(response)
        if not parsed_response["origin_tab"] or not parsed_response["origin_tab"].endswith("</table>"):
            return {"analysis": "Response final table missing </table>.", "is_valid": True, "reward": 0.0}

        parsed_answer = extract_sections(ref_answer)
        pred_table = parsed_response["origin_tab"]
        ref_table = parsed_answer["origin_tab"]

        # --- Base TEDS / TEDS-S (needed for baselines and diagnostics) ---
        base: ClientResponse = _teds_client.call(pred_table, ref_table)
        base_teds, base_teds_s = base.get("teds"), base.get("teds_s")
        if base_teds is None or base_teds_s is None:
            return {"analysis": "Failed to compute base TEDS / TEDS-S.", "is_valid": False, "reward": 0.0}

        # --- R_validity (binary hard gating) ---
        r_validity = validity_reward(
            parsed_response["row_col"],
            parsed_answer["row_col"],
            parsed_response["merge"],
            parsed_answer["merge"],
        )

        # --- R_structure ---
        structure = _compute_structure_reward(pred_table, ref_table, base_teds_s)

        # --- R_content ---
        content = _compute_content_reward(pred_table, ref_table, base_teds, split, ref_destylized)

        # --- Weighted aggregation: R = l1*valid + l2*structure + l3*content ---
        final_reward = weights[0] * r_validity + weights[1] * structure["score"] + weights[2] * content["score"]

        analysis = _build_analysis(
            final_reward,
            weights,
            r_validity,
            structure,
            content,
            {"teds": base_teds, "teds_s": base_teds_s},
            split,
        )

        return {
            "analysis": json.dumps(analysis, ensure_ascii=False, separators=(",", ":")),
            "is_valid": True,
            "reward": final_reward,
        }
    except Exception as e:
        return {
            "analysis": f"Exception during reward computation: {e}",
            "is_valid": False,
            "reward": 0.0,
        }
