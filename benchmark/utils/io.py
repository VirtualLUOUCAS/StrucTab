"""Thread-safe incremental result writer + historical result reader.

Used by the infer / judge stages: every sample is keyed by ``image_path`` and
written into a single jsonl. Concurrent workers submit results and the writer
flushes to disk every ``save_interval`` updates, so a crash never loses the bulk
of the progress.
"""

from __future__ import annotations

import json
import os
import traceback
from threading import Lock

from .signal_utils import install_signal_handlers_once


def get_image_path(row: dict) -> str:
    """Return the normalized relative image path of a row.

    The open-source jsonl uses ``image_path`` as the canonical key; a couple of
    aliases are accepted for robustness.
    """
    for k in ("image_path", "img_path", "image"):
        v = row.get(k)
        if v:
            return v
    return ""


def read_processed(output_file: str) -> dict[str, dict]:
    """Read previously written results, returning an ``image_path -> row`` map.

    A row is considered done when it already carries a non-empty ``response``.
    """
    processed: dict[str, dict] = {}
    if not os.path.isfile(output_file):
        return processed
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = get_image_path(item)
                if not key:
                    continue
                processed[key] = item
    except Exception as e:
        print(f"Error while reading processed data: {e}")
    return processed


class ResultWriter:
    """Periodic flush + full-file replacement; falls back to a .tmp file on error."""

    def __init__(self, output_file: str, processed: dict[str, dict], save_interval: int = 1):
        self.output_file = output_file
        self.processed = processed
        self.lock = Lock()
        self.tmp_file = output_file + ".tmp"
        self.save_interval = save_interval
        self.update_count = 0
        self.last_save_count = 0
        install_signal_handlers_once()

    def update_and_save(self, result: dict, force_save: bool = False) -> None:
        with self.lock:
            key = get_image_path(result)
            if not key:
                return
            self.processed[key] = result
            self.update_count += 1
            if force_save or (self.update_count - self.last_save_count >= self.save_interval):
                self._save_to_disk()
                self.last_save_count = self.update_count

    def _save_to_disk(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.output_file) or ".", exist_ok=True)
            with open(self.tmp_file, "w", encoding="utf-8") as f:
                for data in self.processed.values():
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
            os.rename(self.tmp_file, self.output_file)
        except Exception as e:
            print(f"Error while saving to disk: {e}")
            traceback.print_exc()

    def finalize(self) -> None:
        with self.lock:
            try:
                self._save_to_disk()
            except Exception as e:
                print(f"Error while saving final results: {e}")
                traceback.print_exc()
            finally:
                if os.path.exists(self.tmp_file):
                    try:
                        os.remove(self.tmp_file)
                    except Exception:
                        pass
