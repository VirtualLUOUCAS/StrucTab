"""
Parsing utilities for the sequential-reasoning response format.

A model response is expected to contain three sections in order:

    [Row-Column Analysis]:
    [Merged-Cell Analysis]:
    [Final Table Parsing]:

These markers mirror the curriculum reasoning order described in the paper
(row-column counting -> merged-cell analysis -> HTML parsing).
"""

# Section markers used in the sequential-reasoning format.
SECTION_TAGS = ["【行列数分析】:", "【合并单元格分析】:", "【最终表格解析结果】:"]

# Sentinel produced when a table has no merged cells.
NO_MERGE_TOKEN = "未发现合并单元格。"


def has_all_sections(response: str) -> bool:
    """Return True iff the response contains all three section markers."""
    if not isinstance(response, str):
        raise TypeError("response must be a string")
    return all(tag in response for tag in SECTION_TAGS)


def extract_sections(text: str) -> dict[str, str | None]:
    """
    Split a response into its three sections.

    Returns a dict with keys ``row_col``, ``merge`` and ``origin_tab``; any field
    that cannot be parsed is left as ``None``.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result: dict[str, str | None] = {"row_col": None, "merge": None, "origin_tab": None}

    try:
        _, rest = text.split(SECTION_TAGS[0], 1)
        section_row_col, rest = rest.split(SECTION_TAGS[1], 1)
        section_merge, section_table = rest.split(SECTION_TAGS[2], 1)

        result["row_col"] = section_row_col.strip()
        result["merge"] = section_merge.strip()
        result["origin_tab"] = section_table.strip()
    except ValueError:
        # Any split failure leaves the corresponding fields as None.
        pass

    return result
