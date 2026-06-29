"""
Validity reward (R_validity) of Uni-TabRL.

As described in the paper, the validity reward is a binary hard-gating signal:
it equals 1 only when the prerequisite structural outputs are exactly correct,
i.e. both the row-column counting and the merged-cell analysis match the
reference; otherwise it is 0. This forces the model to first master basic
structural validity before fine-grained optimization.
"""

from .utils import merge_correct, row_col_correct


def validity_reward(
    pred_row_col: str | None,
    ref_row_col: str | None,
    pred_merge: str | None,
    ref_merge: str | None,
) -> float:
    """Binary validity reward: 1.0 iff both prerequisite outputs are exact."""
    if row_col_correct(pred_row_col, ref_row_col) and merge_correct(pred_merge, ref_merge):
        return 1.0
    return 0.0
