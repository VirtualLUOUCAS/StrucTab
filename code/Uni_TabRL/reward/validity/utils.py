"""Helper functions for the validity reward."""

import re

from ..utils.parsing import NO_MERGE_TOKEN

_MERGE_PATTERN = re.compile(r"<merge>.*?</merge>")


def row_col_correct(pred_row_col: str | None, ref_row_col: str | None) -> bool:
    """Row-column counting is correct iff the two descriptions match exactly."""
    return pred_row_col == ref_row_col


def merge_correct(pred_merge: str | None, ref_merge: str | None) -> bool:
    """
    Merged-cell analysis is correct iff every reference merge region is present
    and there are no extra predicted regions (an exact match, i.e. ratio == 1).
    """
    if ref_merge is None or pred_merge is None:
        return False

    # Case 1: the reference table has no merged cells.
    if ref_merge == NO_MERGE_TOKEN:
        return NO_MERGE_TOKEN in pred_merge

    # Case 2: compare the sets of merge regions.
    ref_merges = _MERGE_PATTERN.findall(ref_merge)
    pred_merges = _MERGE_PATTERN.findall(pred_merge)
    if not ref_merges:
        return False

    hit = sum(1 for m in ref_merges if m in pred_merge)
    ratio = hit / max(len(pred_merges), len(ref_merges))
    return ratio == 1.0
