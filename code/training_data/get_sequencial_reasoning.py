"""
表格处理流水线脚本

功能：
- Step1: 解析表格，提取行列数、纯文本表格和结构
- Step2: 清空单元格内容，生成 plain_structure
- Step3: 解析合并单元格信息
- Step4: 生成思维链 (think_tab)

使用方式：
1. 配置 INPUT_FILES 列表
2. 运行: python process.py

输出格式：
- 输入: file.jsonl
- 输出: file_processed.jsonl
- 失败: file_failed.jsonl
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup, NavigableString
from tqdm import tqdm

INPUT_FILES = [
    "your/path/to/table_data.jsonl",
]

MAX_WORKERS = 64


# ======================================
# Step 1: 解析表格基本信息
# ======================================
def strip_text_in_tags(html_str: str) -> str:
    """删除所有 HTML 标签中的文本，只保留结构。"""
    return re.sub(r">([^<>]*)<", r"><", html_str)


def parse_html_table(html_str: str) -> tuple[int, int, list[list[str]]]:
    """解析表格文本，返回行数、列数、纯文本二维表。"""
    soup = BeautifulSoup(html_str, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")

    parsed = []
    for row in rows:
        cells = row.find_all(["td", "th"])
        parsed.append([cell.get_text(strip=True) for cell in cells])

    row_count = len(parsed)
    col_count = max((len(r) for r in parsed), default=0)

    return row_count, col_count, parsed


# ======================================
# Step 2: 生成空结构（plain_structure）
# ======================================
def clean_table_content(html_str: str) -> str:
    """
    使用 BeautifulSoup 清空所有 td/th 内部内容，
    完全保留结构和属性。
    """
    soup = BeautifulSoup(html_str, "html.parser")

    # 清空所有单元格内容
    for cell in soup.find_all(["td", "th"]):
        cell.clear()

    # 清理 <tr> 中的 stray text
    for tr in soup.find_all("tr"):
        for content in list(tr.contents):
            if isinstance(content, NavigableString):
                content.extract()

    return str(soup)


# ======================================
# Step 3: 解析合并单元格
# ======================================
def parse_merges(html) -> str:
    """解析 HTML 表格的合并单元格信息"""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")

    # 动态扩展网格
    grid = []
    merges = []

    for r, tr in enumerate(rows):
        # 确保当前行存在
        while len(grid) <= r:
            grid.append([])

        c = 0

        # 跳过被上方 rowSpan 占据的格子
        while c < len(grid[r]) and grid[r][c] is not None:
            c += 1

        # 遍历当前行的 td/th
        for cell in tr.find_all(["td", "th"]):
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))

            # 找到当前行中的下一个空格
            while c < len(grid[r]) and grid[r][c] is not None:
                c += 1

            # 左上角坐标（1-based）
            r1 = r + 1
            c1 = c + 1

            # 右下角坐标（1-based）
            r2 = r + rowspan
            c2 = c + colspan

            # 填充被 rowspan/colspan 占据的所有格子
            for rr in range(r, r + rowspan):
                # 确保 grid 的行存在
                while len(grid) <= rr:
                    grid.append([])

                # 确保该行列数组长度足够
                while len(grid[rr]) < c + colspan:
                    grid[rr].append(None)

                # 填充占位
                for cc in range(c, c + colspan):
                    grid[rr][cc] = (r, c)

            # 如果有合并，则记录 merge
            if rowspan > 1 or colspan > 1:
                merges.append(f"<merge>({r1},{c1}),({r2},{c2})</merge>")

            c += colspan  # 移动列指针

    merge_str = "".join(merges)
    return merge_str if merge_str.strip() else "未发现合并单元格。"


# ======================================
# Step 4: 生成思维链
# ======================================
def generate_thinking_chain(row_count: int, col_count: int, merge_info: str, origin_tab: str) -> str:
    """生成思维链"""

    step1_str = f"【行列数分析】:\n这是一个{row_count}行{col_count}列的表格。"
    step2_str = f"【合并单元格分析】:\n{merge_info}"
    step3_str = f"【最终表格解析结果】:\n{origin_tab}"

    return step1_str + "\n\n" + step2_str + "\n\n" + step3_str


def _get_img_path(data: dict) -> str | None:
    """从数据对象中提取 img_path 字段"""
    if "img_path_gy" in data and data["img_path_gy"]:
        return data["img_path_gy"]
    elif "img_path_sh" in data and data["img_path_sh"]:
        return data["img_path_sh"]
    elif "img_path" in data and data["img_path"]:
        return data["img_path"]
    else:
        return None


def _get_answer(data: dict) -> str | None:
    """从数据对象中提取 answer 字段"""
    if "conv" in data and data["conv"]:
        answer = data["conv"][0].get("answer", "")
    elif "anno" in data and data["anno"]:
        answer = data["anno"]
    elif "tab_anno" in data and data["tab_anno"]:
        answer = data["tab_anno"]
    elif "ref_ans" in data and data["ref_ans"]:
        answer = data["ref_ans"]
    elif "answer" in data and data["answer"]:
        answer = data["answer"]
    elif "answers" in data and data["answers"]:
        answer = data["answers"]
    else:
        answer = None

    if isinstance(answer, list) and answer:
        answer = answer[0]

    return answer


# ======================================
# 单行处理逻辑
# ======================================
# 返回值: (status, result_or_raw_obj, error_msg)
# status: "success" | "skip" | "failed"
def process_single_line(line: str) -> tuple[str, dict | None, str]:
    """处理单行 JSON，返回 (status, result_dict, error_msg)"""
    line = line.strip()
    if not line:
        return "skip", None, ""

    # JSON 解析
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        return "failed", {"__raw__": line}, f"JSON 解析错误: {e}"

    # 检查 image_path
    img_path = _get_img_path(obj)
    if img_path is None or not isinstance(img_path, str) or not img_path:
        return "skip", None, "无有效 img_path"
    if not os.path.exists(img_path):
        return "skip", None, f"图片路径不存在: {img_path}"

    # 检查 answer
    answer = _get_answer(obj)
    if answer is None or not isinstance(answer, str) or not answer:
        return "skip", None, "无有效 answer"

    answer = answer.strip()

    # 过滤：必须是完整的单表格
    match = re.search(r"<table.*?>.*?</table>", answer, re.DOTALL)
    if not match:
        return "skip", None, f"非完整表格: {answer[:30]}..."

    answer = match.group(0)

    table_start_count = len(re.findall(r"<table[^>]*>", answer))
    table_end_count = answer.count("</table>")
    if table_start_count != 1 or table_end_count != 1:
        return "skip", None, f"非完整表格: {answer[:30]}..."

    # 核心处理
    try:
        if "row_count" in obj and "col_count" in obj and "merge" in obj:
            row_count = obj["row_count"]
            col_count = obj["col_count"]
            merge_info = obj["merge"]
            parsed_table = None
            structure_html = None
            plain_structure = None
        else:
            row_count, col_count, parsed_table = parse_html_table(answer)
            structure_html = strip_text_in_tags(answer)
            plain_structure = clean_table_content(answer)
            merge_info = parse_merges(plain_structure)

        think_tab = generate_thinking_chain(row_count, col_count, merge_info, answer)

        result = {
            "img_path": img_path,
            "origin_tab": answer,
            "row_count": row_count,
            "col_count": col_count,
            "table": parsed_table,
            "structure": structure_html,
            "plain_structure": plain_structure,
            "merge": merge_info,
            "think_tab": think_tab,
        }
        for key in ("question", "category", "l2-category", "split"):
            if key in obj:
                result[key] = obj[key]

        return "success", result, ""

    except KeyError as e:
        return "failed", obj, f"缺少必需字段: {e}"
    except Exception as e:
        return "failed", obj, f"处理错误: {e}"


# ======================================
# 主处理流程
# ======================================
def process_single_file(input_path: str):
    """处理单个 JSONL 文件，并行执行完整的四步流程"""
    output_path = input_path.replace(".jsonl", "_processed.jsonl")
    failed_path = input_path.replace(".jsonl", "_failed.jsonl")

    print(f"\n📖 处理文件: {os.path.basename(input_path)}")
    print(f"   输出路径: {output_path}")
    print(f"   失败路径: {failed_path}")
    print(f"   并发数:   {MAX_WORKERS}")

    stats = {
        "total": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }

    # 读取所有行
    with open(input_path, "r", encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]

    stats["total"] = len(lines)

    # 并行处理，保持原始顺序
    results = [None] * len(lines)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(process_single_line, line): i for i, line in enumerate(lines)}

        with tqdm(total=len(lines), desc="处理数据", unit="行") as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    # 兜底：理论上 process_single_line 内部已捕获
                    results[idx] = ("failed", {"__raw__": lines[idx].strip()}, f"未捕获异常: {e}")
                pbar.update(1)

    # 按顺序写入结果
    with open(output_path, "w", encoding="utf-8") as outfile, open(failed_path, "w", encoding="utf-8") as failfile:
        for i, (status, data, err_msg) in enumerate(results):
            if status == "success":
                json.dump(data, outfile, ensure_ascii=False)
                outfile.write("\n")
                stats["success"] += 1

            elif status == "failed":
                # 原样输出到 failed 文件
                raw = data.get("__raw__") if "__raw__" in data else json.dumps(data, ensure_ascii=False)
                failfile.write(raw + "\n")
                stats["failed"] += 1
                if err_msg:
                    print(f"\n⚠️  行 {i + 1} 失败: {err_msg}")

            else:  # skip
                stats["skipped"] += 1

    # 输出统计
    print("\n✅ 处理完成:")
    print(f"   总行数:      {stats['total']:,}")
    print(f"   成功处理:    {stats['success']:,}")
    print(f"   跳过:        {stats['skipped']:,}")
    print(f"   失败(已保存): {stats['failed']:,}")

    if stats["total"] > 0:
        success_rate = stats["success"] / stats["total"] * 100
        print(f"   成功率:      {success_rate:.2f}%")

    return stats


def main():
    print("=" * 80)
    print("🔧 表格处理流水线")
    print("功能: 解析表格 → 生成结构 → 提取合并信息 → 生成思维链")
    print("=" * 80)

    total_stats = {"files": 0, "total_lines": 0, "total_success": 0, "total_failed": 0, "total_skipped": 0}

    for input_file in INPUT_FILES:
        if not os.path.exists(input_file):
            print(f"\n❌ 文件不存在: {input_file}")
            continue

        stats = process_single_file(input_file)

        total_stats["files"] += 1
        total_stats["total_lines"] += stats["total"]
        total_stats["total_success"] += stats["success"]
        total_stats["total_failed"] += stats["failed"]
        total_stats["total_skipped"] += stats["skipped"]

    print("\n" + "=" * 80)
    print("📊 总体统计")
    print("=" * 80)
    print(f"处理文件数: {total_stats['files']}")
    print(f"总行数:     {total_stats['total_lines']:,}")
    print(f"成功处理:   {total_stats['total_success']:,}")
    print(f"跳过:       {total_stats['total_skipped']:,}")
    print(f"失败:       {total_stats['total_failed']:,}")

    if total_stats["total_lines"] > 0:
        success_rate = total_stats["total_success"] / total_stats["total_lines"] * 100
        print(f"总成功率:   {success_rate:.2f}%")

    print("\n✅ 所有文件处理完成！")


if __name__ == "__main__":
    main()
