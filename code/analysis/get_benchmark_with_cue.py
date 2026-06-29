"""
Build the four "structural cue" prompt variants used for the
"Impact of explicit structural cues" experiment (Fig. 4a).

For each table sample we generate four prompts:

    direct     : no structural cue (baseline)
    with_size  : row/column counts provided as a cue
    with_merge : merged-cell information provided as a cue
    with_both  : both cues provided

Each output record keeps only the generic fields: id / image_path / question / answer.
"""

import json
import os
import re

INPUT_FILES = [
    "your/path/to/CC_OCR.jsonl",
    "your/path/to/OCRBench.jsonl",
    "your/path/to/OmniDocBench.jsonl",
    "your/path/to/TableVerse_5K.jsonl",
]

# Whether to reuse the question stored in the data; otherwise use BASE_INSTRUCTION.
USE_DATA_QUESTION = False

BASE_INSTRUCTION = (
    "You are an AI specialized in recognizing and extracting table from images. "
    "Your mission is to analyze the table image and generate the result in HTML format using specified tags."
)
SUFFIX_INSTRUCTION = "Output only the results without any other words and explanation."

NO_MERGE_TOKEN = "未发现合并单元格。"


def parse_merge_cells(merge_str: str) -> str:
    """Convert a ``<merge>...</merge>`` string into a natural-language description."""
    if not merge_str or merge_str == NO_MERGE_TOKEN:
        return "There are no merged cells in the table."

    merge_pattern = r"<merge>\((\d+),(\d+)\),\((\d+),(\d+)\)</merge>"
    matches = re.findall(merge_pattern, merge_str)
    if not matches:
        return "There are no merged cells in the table."

    descriptions = [f"cells from row {r1} column {c1} to row {r2} column {c2} are merged" for r1, c1, r2, c2 in matches]
    return "; ".join(descriptions) + "."


def generate_questions(row_count: int, col_count: int, merge_str: str, data_question: str | None) -> dict:
    """Generate the four cue-variant prompts for one table."""
    merge_description = parse_merge_cells(merge_str)
    base = data_question if (USE_DATA_QUESTION and data_question) else BASE_INSTRUCTION

    return {
        "direct": f"{base}\n{SUFFIX_INSTRUCTION}",
        "with_size": f"{base}\nThe table has {row_count} rows and {col_count} columns.\n{SUFFIX_INSTRUCTION}",
        "with_merge": f"{base}\nThe merged cells of table: {merge_description}\n{SUFFIX_INSTRUCTION}",
        "with_both": (
            f"{base}\n"
            f"The table has {row_count} rows and {col_count} columns.\n"
            f"The merged cells of table: {merge_description}\n"
            f"{SUFFIX_INSTRUCTION}"
        ),
    }


def gen_output_paths(input_file: str) -> dict:
    """Derive the four output file paths from an input file path."""
    base_path = input_file.replace(".jsonl", "")
    return {key: f"{base_path}_{key}.jsonl" for key in ("direct", "with_size", "with_merge", "with_both")}


def _extract_image_path(data: dict, input_file: str) -> str | None:
    if "render_path" in data and data["render_path"] and "render" in input_file:
        return data["render_path"]
    for key in ("img_path", "image_path"):
        if data.get(key):
            return data[key]
    return None


def _extract_answer(data: dict) -> str | None:
    if data.get("conv"):
        return data["conv"][0]["answer"]
    for key in ("anno", "answer", "origin_tab"):
        if data.get(key):
            return data[key]
    if data.get("merge"):
        return data.get("tab_anno", data.get("origin_tab", ""))
    return None


def build_cue_variants(input_file: str) -> None:
    """Read one benchmark file and write the four cue-variant files."""
    output_paths = gen_output_paths(input_file)
    for output_file in output_paths.values():
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

    output_files = {key: open(path, "w", encoding="utf-8") for key, path in output_paths.items()}
    try:
        with open(input_file, "r", encoding="utf-8") as f_in:
            for index, line in enumerate(f_in):
                if not line.strip():
                    continue
                data: dict = json.loads(line.strip())

                image_path = _extract_image_path(data, input_file)
                if image_path is None:
                    print(f"Missing image path, skip index={index}")
                    continue

                answer = _extract_answer(data)
                if answer is None:
                    print(f"Missing answer, skip index={index}")
                    continue

                row_count = data.get("row_count", 0)
                col_count = data.get("col_count", 0)
                merge_info = data.get("merge", NO_MERGE_TOKEN)
                data_question = data.get("question")

                questions = generate_questions(row_count, col_count, merge_info, data_question)
                for key, question in questions.items():
                    record = {
                        "id": str(index),
                        "image_path": image_path,
                        "question": question,
                        "answer": answer,
                    }
                    output_files[key].write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"Done: {input_file}")
        for key, path in output_paths.items():
            print(f"  - {key}: {path}")
    finally:
        for f_out in output_files.values():
            f_out.close()


if __name__ == "__main__":
    for input_file in INPUT_FILES:
        if os.path.exists(input_file):
            build_cue_variants(input_file)
        else:
            print(f"File not found: {input_file}")
