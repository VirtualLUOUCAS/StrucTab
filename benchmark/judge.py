"""TableVerse-5K table-parsing judging entry point.

Scoring is delegated to a standalone TEDS judging service. Start the service
from ``StrucTab/code/Uni_TabRL/server/TEDS_judger`` (its ``run.sh`` launches a
pool of uvicorn workers exposing ``/judge/simple``), then list the resulting
``host:port`` endpoints in ``judger_server.json`` next to this script.

Usage:
    # Judge all models under infer_results/
    python judge.py

    # Judge specific models only
    python judge.py --models Qwen2.5-VL-7B-Instruct gemini-2.5-pro

Outputs:
    judge_results/<model_tag>/results.jsonl   # per-sample TEDS / TEDS-S
    judge_results/evaluation_results.xlsx     # aggregated leaderboard
"""

from __future__ import annotations

import argparse
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parent

DEFAULT_DATA_FILE = REPO_ROOT / "data" / "TableVerse_5K.jsonl"
DEFAULT_INFER_DIR = REPO_ROOT / "infer_results"
DEFAULT_JUDGE_DIR = REPO_ROOT / "judge_results"
DEFAULT_SERVER_JSON = REPO_ROOT / "judger_server.json"

SIMPLE_ROUTER = "/judge/simple"
DEFAULT_PROXIES = {"http": "", "https": ""}
TIMEOUT = 60


def get_image_path(row: dict) -> str:
    for k in ("image_path", "img_path", "image"):
        v = row.get(k)
        if v:
            return v
    return ""


def extract_table_content(text: str) -> str:
    """Extract the ``<table>...</table>`` block from text, else return the text."""
    if not text:
        return text
    match = re.search(r"<table[\s\S]*?</table>", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(0).strip()
    return text


def postprocess_model_response(response: str) -> str:
    """Normalize a model response into a bare ``<table>...</table>`` string."""
    if not response:
        return response

    response = response.strip()

    # Strip a ```html ... ``` / ``` ... ``` markdown fence if present.
    match = re.search(r"```html\s*\n(.*?)\n```", response, re.DOTALL | re.IGNORECASE)
    if match:
        response = match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    if match:
        response = match.group(1).strip()

    response = (
        response.replace("<th>", "<td>")
        .replace("</th>", "</td>")
        .replace("<thead>", "")
        .replace("</thead>", "")
        .replace("<tbody>", "")
        .replace("</tbody>", "")
    )

    return extract_table_content(response)


def load_servers(server_json: Path) -> list[str]:
    if not server_json.is_file():
        raise SystemExit(
            f"endpoint list not found: {server_json}\n"
            "Start the TEDS judging service (StrucTab/code/Uni_TabRL/server/TEDS_judger/run.sh) "
            "and fill its host:port endpoints into this file."
        )
    with open(server_json, "r", encoding="utf-8") as f:
        hosts = json.load(f)
    hosts = [h for h in hosts if h and "your." not in h]
    if not hosts:
        raise SystemExit(
            f"no valid endpoint configured in {server_json}; "
            "replace the placeholders with real host:port entries."
        )
    return hosts


class TableParsingJudgeClient:
    """Round-robin client over a pool of TEDS judging endpoints.

    After two full passes over the endpoint list it reshuffles and starts over,
    spreading load evenly across all workers.
    """

    def __init__(self, servers: list[str]):
        self._lock = threading.Lock()
        self.servers = [f"http://{host}" for host in servers]
        self._index = 0
        self._reshuffle()

    def _reshuffle(self):
        shuffled = list(self.servers)
        random.shuffle(shuffled)
        self._index = 0
        self._shuffled = shuffled

    def get_next_server(self) -> str | None:
        with self._lock:
            if not self._shuffled:
                return None
            if self._index >= len(self._shuffled) * 2:
                self._reshuffle()
            server = self._shuffled[self._index % len(self._shuffled)]
            self._index += 1
            return server

    def call(self, response: str, ref_answer: str, max_retry: int = 3) -> dict:
        """Score a single (response, ref_answer) pair via ``/judge/simple``.

        Returns ``{"teds": float, "teds_s": float, "error": str | None}``.
        """
        response = postprocess_model_response(response)
        ref_answer = postprocess_model_response(ref_answer)
        payload = {"response": response, "ref_answer": ref_answer}

        eval_score = {"teds": 0.0, "teds_s": 0.0, "error": None}
        if not response:
            eval_score["error"] = "empty response"
            return eval_score

        for attempt in range(max_retry):
            base_url = self.get_next_server()
            if base_url is None:
                continue
            try:
                resp = requests.post(
                    base_url + SIMPLE_ROUTER, json=payload, timeout=TIMEOUT, proxies=DEFAULT_PROXIES
                )
                if resp.status_code == 200:
                    result = resp.json()
                    return {
                        "teds": result.get("teds", 0.0),
                        "teds_s": result.get("teds_s", 0.0),
                        "error": None,
                    }
            except Exception as e:
                if attempt == max_retry - 1:
                    eval_score["error"] = f"judge call failed after {max_retry} attempts: {e}"
            time.sleep(0.5 * (attempt + 1))

        return eval_score


def load_gt_index(data_file: Path) -> dict[str, str]:
    """Load the GT jsonl, mapping image_path -> ref_answer."""
    index: dict[str, str] = {}
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = get_image_path(row)
            if key:
                index[key] = row.get("ref_answer", "")
    return index


def judge_one_row(client: TableParsingJudgeClient, infer_row: dict, ref_answer: str) -> dict:
    response = infer_row.get("response", "")
    if isinstance(response, list):
        response = response[0] if response else ""
    eval_score = client.call(response, ref_answer)
    out = dict(infer_row)
    out["eval_score"] = eval_score
    return out


def judge_one_model(
    client: TableParsingJudgeClient,
    model_tag: str,
    infer_file: Path,
    output_file: Path,
    gt_index: dict[str, str],
    max_workers: int,
) -> dict:
    infer_rows: list[dict] = []
    with open(infer_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            infer_rows.append(json.loads(line))

    pairs: list[tuple[dict, str]] = []
    missing = 0
    for r in infer_rows:
        key = get_image_path(r)
        ref = gt_index.get(key)
        if ref is None:
            # Fall back to the ref_answer kept inside the infer row, if any.
            ref = r.get("ref_answer")
        if ref is None:
            missing += 1
            continue
        pairs.append((r, ref))

    output_file.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    teds_list: list[float] = []
    teds_s_list: list[float] = []

    if pairs:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(judge_one_row, client, r, ref): r for r, ref in pairs}
            for fut in tqdm(as_completed(futures), total=len(futures), desc=f"judge[{model_tag}]"):
                res = fut.result()
                results.append(res)
                score = res.get("eval_score", {})
                if score.get("error") is None:
                    teds_list.append(score.get("teds", 0.0))
                    teds_s_list.append(score.get("teds_s", 0.0))

    with open(output_file, "w", encoding="utf-8") as f:
        for res in results:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")

    n = len(teds_list)
    avg = {
        "model_name": model_tag,
        "teds": sum(teds_list) / n if n else 0.0,
        "teds_s": sum(teds_s_list) / n if n else 0.0,
        "total_items": len(infer_rows),
        "scored_items": n,
        "missing_in_gt": missing,
    }
    final_rst_path = output_file.parent / "final_rst.json"
    with open(final_rst_path, "w", encoding="utf-8") as f:
        json.dump(avg, f, ensure_ascii=False, indent=2)
    return avg


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TableVerse-5K table-parsing judging (TEDS / TEDS-S)")
    p.add_argument("--data_file", type=str, default=str(DEFAULT_DATA_FILE), help="benchmark jsonl path")
    p.add_argument("--infer_dir", type=str, default=str(DEFAULT_INFER_DIR), help="infer_results directory")
    p.add_argument("--output_dir", type=str, default=str(DEFAULT_JUDGE_DIR), help="judge_results directory")
    p.add_argument("--server_json", type=str, default=str(DEFAULT_SERVER_JSON), help="TEDS endpoint list JSON path")
    p.add_argument(
        "--models", type=str, nargs="*", default=None, help="only judge these models; default scans all sub-dirs of infer_dir"
    )
    p.add_argument("--max_workers", type=int, default=64)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    data_file = Path(args.data_file).resolve()
    if not data_file.is_file():
        raise SystemExit(f"benchmark file not found: {data_file}")

    infer_dir = Path(args.infer_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not infer_dir.is_dir():
        raise SystemExit(f"infer dir not found: {infer_dir}")

    servers = load_servers(Path(args.server_json).resolve())
    client = TableParsingJudgeClient(servers)

    print("=" * 72)
    print("TableVerse-5K Judging")
    print("=" * 72)
    print(f"data_file  : {data_file}")
    print(f"infer_dir  : {infer_dir}")
    print(f"output_dir : {output_dir}")
    print(f"endpoints  : {len(servers)}")

    gt_index = load_gt_index(data_file)
    print(f"GT samples : {len(gt_index)}")

    if args.models:
        model_tags = args.models
    else:
        model_tags = sorted(d.name for d in infer_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
    print(f"models     : {len(model_tags)} -> {model_tags}\n")

    summary: list[dict] = []
    for tag in model_tags:
        infer_file = infer_dir / tag / "results.jsonl"
        if not infer_file.is_file():
            print(f"[{tag}] skip: {infer_file} not found")
            continue
        output_file = output_dir / tag / "results.jsonl"
        avg = judge_one_model(client, tag, infer_file, output_file, gt_index, max_workers=args.max_workers)
        summary.append(avg)
        print(
            f"[{tag}] TEDS={avg['teds']:.4f}  TEDS-S={avg['teds_s']:.4f}  "
            f"scored={avg['scored_items']}/{avg['total_items']}  missing_in_gt={avg['missing_in_gt']}"
        )

    print("\n" + "=" * 72)
    print("Summary")
    print("=" * 72)
    for avg in summary:
        print(f"  {avg['model_name']:40s}  TEDS={avg['teds'] * 100:6.2f}  TEDS-S={avg['teds_s'] * 100:6.2f}")

    if summary:
        excel_path = output_dir / "evaluation_results.xlsx"
        df = pd.DataFrame(
            [
                {
                    "Model": a["model_name"],
                    "TEDS": round(a["teds"] * 100, 4),
                    "TEDS-S": round(a["teds_s"] * 100, 4),
                    "Scored": a["scored_items"],
                    "Total": a["total_items"],
                }
                for a in summary
            ]
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        df.to_excel(excel_path, index=False, sheet_name="Evaluation Results")
        print(f"\nExcel report saved to: {excel_path}")

    print("\nJudging completed!")


if __name__ == "__main__":
    main()
