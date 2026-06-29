"""TableVerse-5K table-parsing inference entry point.

Usage:
    # 1) Local OpenAI-compatible service started by ``vllm serve`` / sglang / lmdeploy
    python infer.py --api_type openai_compat \
        --model_name Qwen2.5-VL-7B-Instruct \
        --base_url http://127.0.0.1:8000/v1 \
        --api_key EMPTY

    # 2) In-process vLLM, point ``--model_path`` to a local checkpoint
    python infer.py --api_type local_vllm \
        --model_path /path/to/checkpoint \
        --tensor_parallel_size 4

Inputs:
    data/TableVerse_5K.jsonl, where each line is
        {"image_path": "images/xxx.jpg", "question": "...", "ref_answer": "<table>...</table>"}
    ``image_path`` is relative to the data file directory and is the unique key.

Outputs:
    infer_results/<model_tag>/results.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tqdm

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from apis import API_TYPES, get_api  # noqa: E402
from utils.io import ResultWriter, get_image_path, read_processed  # noqa: E402
from utils.signal_utils import ABORT_EVENT, install_signal_handlers_once  # noqa: E402

# ============================================================
# Configuration
# ============================================================
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "TableVerse_5K.jsonl"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "infer_results"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TableVerse-5K table-parsing inference")

    # API selection
    p.add_argument(
        "--api_type",
        choices=API_TYPES,
        required=True,
        help="local_vllm: in-process vllm.LLM; openai_compat: standard OpenAI protocol",
    )

    # openai_compat args
    p.add_argument("--model_name", type=str, default=None, help="the model field used by openai_compat")
    p.add_argument("--base_url", type=str, default=None, help="openai_compat service, e.g. http://127.0.0.1:8000/v1")
    p.add_argument("--api_key", type=str, default="EMPTY")

    # local_vllm args
    p.add_argument("--model_path", type=str, default=None, help="local_vllm: local model checkpoint path")
    p.add_argument("--tensor_parallel_size", type=int, default=1)
    p.add_argument("--max_model_len", type=int, default=None)
    p.add_argument("--gpu_memory_utilization", type=float, default=0.9)

    # data / output
    p.add_argument(
        "--data_file", type=str, default=str(DEFAULT_DATA_FILE), help=f"benchmark jsonl path, default {DEFAULT_DATA_FILE}"
    )
    p.add_argument("--output_dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument(
        "--output_tag", type=str, default=None, help="result sub-dir name, default inferred from model_name / model_path"
    )

    # inference params
    p.add_argument("--max_workers", type=int, default=64)
    p.add_argument("--max_try", type=int, default=3)
    p.add_argument("--max_rows", type=int, default=-1)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--save_interval", type=int, default=1)
    p.add_argument("--debug", action="store_true")

    return p.parse_args()


def build_api(args: argparse.Namespace):
    if args.api_type == "openai_compat":
        if not args.model_name or not args.base_url:
            raise ValueError("--api_type openai_compat requires both --model_name and --base_url")
        return get_api(
            "openai_compat",
            model_name=args.model_name,
            base_url=args.base_url,
            api_key=args.api_key,
            max_try=args.max_try,
        )
    elif args.api_type == "local_vllm":
        if not args.model_path:
            raise ValueError("--api_type local_vllm requires --model_path")
        return get_api(
            "local_vllm",
            model_path=args.model_path,
            tensor_parallel_size=args.tensor_parallel_size,
            max_model_len=args.max_model_len,
            gpu_memory_utilization=args.gpu_memory_utilization,
            temperature=args.temperature,
            max_try=args.max_try,
        )
    else:
        raise ValueError(f"unsupported api_type: {args.api_type}")


def derive_output_tag(args: argparse.Namespace) -> str:
    if args.output_tag:
        return args.output_tag
    if args.api_type == "openai_compat" and args.model_name:
        return args.model_name
    if args.api_type == "local_vllm" and args.model_path:
        return Path(args.model_path).name
    return "default"


def resolve_image_path(row: dict, data_file_dir: Path) -> str:
    """``image_path`` in the open-source jsonl is relative to the data dir; turn
    it into an absolute path."""
    rel = get_image_path(row)
    if not rel:
        return ""
    if os.path.isabs(rel):
        return rel
    return str(data_file_dir / rel)


def process_one_row(
    api_instance,
    row: dict,
    abs_img_path: str,
    temperature: float,
) -> dict | None:
    """Run inference for a single sample. Returns a new row carrying ``response``."""
    if not abs_img_path or not os.path.exists(abs_img_path):
        print(f"warning: image not found {abs_img_path}")
        return None

    question = row.get("question", "") or ""

    ok, _thinking, answer = api_instance(abs_img_path, question, temperature=temperature)
    if not ok:
        answer = ""

    result = dict(row)
    result["image_path"] = get_image_path(row)  # keep the relative path as the key
    result["response"] = answer
    return result


def main() -> None:
    args = parse_args()

    data_file = Path(args.data_file).resolve()
    if not data_file.is_file():
        raise SystemExit(
            f"benchmark file not found: {data_file}\n"
            "Download the TableVerse-5K dataset and place it under data/ "
            "(see benchmark/data/.gitkeep)."
        )
    data_dir = data_file.parent

    output_tag = derive_output_tag(args)
    output_dir = Path(args.output_dir).resolve() / output_tag
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "results.jsonl"

    print("=" * 72)
    print("TableVerse-5K Inference")
    print("=" * 72)
    print(f"api_type     : {args.api_type}")
    print(f"output_tag   : {output_tag}")
    print(f"data_file    : {data_file}")
    print(f"output_file  : {output_file}")
    print(f"max_workers  : {args.max_workers}")
    print(f"max_rows     : {args.max_rows if args.max_rows > 0 else 'all'}")
    print(f"temperature  : {args.temperature}")

    # Read jsonl
    rows: list[dict] = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if args.max_rows > 0:
        rows = rows[: args.max_rows]
    if args.debug:
        rows = rows[: min(5, len(rows))]
    print(f"loaded {len(rows)} rows")

    # API
    print("\nInitializing API...")
    api_instance = build_api(args)
    print("API ready")

    # Historical results (incremental / resume)
    processed = read_processed(str(output_file))
    print(f"history: {len(processed)} rows already written")

    # Pending list: a row is done when it already has a non-empty response.
    pending: list[tuple[dict, str]] = []
    fully_done = 0
    for row in rows:
        rel = get_image_path(row)
        if not rel:
            continue
        prev = processed.get(rel)
        if prev and prev.get("response"):
            fully_done += 1
            continue
        abs_img = resolve_image_path(row, data_dir)
        pending.append((row, abs_img))

    print(f"fully done: {fully_done}, pending: {len(pending)}\n")
    if not pending:
        print("nothing to process")
        return

    install_signal_handlers_once()
    writer = ResultWriter(str(output_file), processed, save_interval=args.save_interval)

    executor = ThreadPoolExecutor(max_workers=args.max_workers)
    aborted = False
    try:
        futures = {
            executor.submit(process_one_row, api_instance, row, abs_img, args.temperature): row
            for row, abs_img in pending
        }
        pbar = tqdm.tqdm(total=len(futures), desc="inference")
        for fut in concurrent.futures.as_completed(futures):
            if ABORT_EVENT.is_set():
                aborted = True
                break
            try:
                result = fut.result()
                if result:
                    writer.update_and_save(result)
            except Exception as e:
                print(f"\nfailed: {e}")
                traceback.print_exc()
            pbar.update(1)
        pbar.close()
        if aborted:
            for f in futures:
                if not f.done():
                    f.cancel()
    finally:
        if ABORT_EVENT.is_set():
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True)

    print("\nflushing final results...")
    writer.finalize()
    print(f"inference done: {output_file}")
    if ABORT_EVENT.is_set():
        sys.exit(130)


if __name__ == "__main__":
    main()
