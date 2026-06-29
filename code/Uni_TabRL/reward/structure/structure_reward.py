"""
Structure reward (R_structure) of Uni-TabRL.

Two variants are supported:

    - ``teds_s``   : the holistic structure-only TEDS score (baseline).
    - ``1d_probe`` : the proposed 1D Probe structural reward.

The 1D Probe linearizes both the predicted and reference tables into a 1-D
sequence of cells (row by row, left to right) and measures the fraction of
cells that match before the first structural mismatch. By rewarding the longest
correct structural prefix, it aligns the optimization signal with the
autoregressive generation order and penalizes early structural divergence.
"""

from bs4 import BeautifulSoup

from .utils import cells_match, extract_cells_with_row


def one_d_probe_reward(pred_structure: str, ref_structure: str) -> dict[str, float | int]:
    """
    Compute the 1D Probe structural reward.

    Args:
        pred_structure: predicted table structure (cell contents already cleared).
        ref_structure:  reference table structure (cell contents already cleared).

    Returns:
        dict with ``score`` (matched / total reference cells, in [0, 1]),
        ``matched_cells`` and ``total_cells``.
    """
    soup_pred = BeautifulSoup(pred_structure, "html.parser")
    soup_ref = BeautifulSoup(ref_structure, "html.parser")

    cells_pred = extract_cells_with_row(soup_pred)
    cells_ref = extract_cells_with_row(soup_ref)
    total_cells = len(cells_ref)

    # Exact structural match.
    if pred_structure == ref_structure:
        return {"score": 1.0, "matched_cells": total_cells, "total_cells": total_cells}

    if total_cells == 0:
        return {"score": 1.0, "matched_cells": 0, "total_cells": 0}

    # Count matched cells until the first mismatch.
    matched_cells = 0
    for i in range(min(total_cells, len(cells_pred))):
        cell_ref, row_ref = cells_ref[i]
        cell_pred, row_pred = cells_pred[i]
        if not cells_match(cell_ref, row_ref, cell_pred, row_pred):
            break
        matched_cells += 1

    return {
        "score": matched_cells / total_cells,
        "matched_cells": matched_cells,
        "total_cells": total_cells,
    }
