import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import openpyxl  # noqa
import pandas as pd
from PIL import Image

INPUT_FILES = [
    "your/path/to/CC_OCR.jsonl",
    "your/path/to/OCRBench.jsonl",
    "your/path/to/OmniDocBench.jsonl",
    "your/path/to/TableVerse_5K.jsonl",
]

OUTPUT_FILE = "your/path/to/data_statistics.xlsx"

MAX_WORKERS = 128


def process_item(item):
    """处理单条数据，返回统计信息。任何字段提取失败则抛出异常。"""
    row_count = int(item["row_count"])
    col_count = int(item["col_count"])

    merge_str = item["merge"]
    merge_count = merge_str.count("<merge>")

    img_path = item["img_path"]
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"图片不存在: {img_path}")
    with Image.open(img_path) as img:
        width, height = img.size

    return {
        "row_count": row_count,
        "col_count": col_count,
        "merge_count": merge_count,
        "width": width,
        "height": height,
    }


def analyze_file(filepath):
    """分析单个 jsonl 文件"""
    items = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    results = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_item, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                failed += 1
                print(f"  [失败] 条目 {futures[future]} 处理出错: {e}")

    total = len(items)
    success = len(results)

    if success == 0:
        return {
            "文件名": os.path.basename(filepath),
            "数据总量": total,
            "成功数量": 0,
            "失败数量": failed,
            "平均行数": "N/A",
            "平均列数": "N/A",
            "平均合并单元格数": "N/A",
            "平均分辨率(宽x高)": "N/A",
        }

    avg_row = sum(r["row_count"] for r in results) / success
    avg_col = sum(r["col_count"] for r in results) / success
    avg_merge = sum(r["merge_count"] for r in results) / success
    avg_width = sum(r["width"] for r in results) / success
    avg_height = sum(r["height"] for r in results) / success

    return {
        "文件名": os.path.basename(filepath),
        "数据总量": total,
        "成功数量": success,
        "失败数量": failed,
        "平均行数": round(avg_row, 2),
        "平均列数": round(avg_col, 2),
        "平均合并单元格数": round(avg_merge, 2),
        "平均分辨率(宽x高)": f"{avg_width:.1f} x {avg_height:.1f}",
    }


def main():
    all_stats = []
    for filepath in INPUT_FILES:
        print(f"正在处理: {filepath}")
        stats = analyze_file(filepath)
        all_stats.append(stats)
        print(
            f"  完成: 总量={stats['数据总量']}, 成功={stats['成功数量']}, 失败={stats['失败数量']}, "
            f"平均行数={stats['平均行数']}, 平均列数={stats['平均列数']}, "
            f"平均合并单元格数={stats['平均合并单元格数']}, 平均分辨率={stats['平均分辨率(宽x高)']}"
        )

    df = pd.DataFrame(all_stats)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"\n统计结果已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
