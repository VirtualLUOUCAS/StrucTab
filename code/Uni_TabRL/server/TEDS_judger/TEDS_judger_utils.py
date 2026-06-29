# ruff: noqa: F601
import difflib  # noqa
import html  # noqa # necessary for lxml parser

import Levenshtein  # noqa # necessary for levenshtein_distance
from bs4 import BeautifulSoup  # noqa # necessary for lxml parser
from Levenshtein import distance as levenshtein_distance  # noqa
from table_recognition_metric import TEDS  # noqa

"""
单个文件实现 Table parsing 任务的评分函数
"""


teds = TEDS()
teds_struct = TEDS(structure_only=True)


def _validate_response_tags(response: str) -> bool:
    if not isinstance(response, str):
        raise TypeError("response must be a string")

    required_tags = [
        "【行列数分析】:",
        "【合并单元格分析】:",
        "【最终表格解析结果】:",
    ]

    missing: list[str] = [tag for tag in required_tags if tag not in response]

    if missing:
        return False

    return True


def _extract_by_sections(text: str) -> dict[str, str | None]:
    """
    使用以下三个固定分隔符进行拆分：
      【行列数分析】:
      【合并单元格分析】:
      【最终表格解析结果】:
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    tags = [
        "【行列数分析】:",
        "【合并单元格分析】:",
        "【最终表格解析结果】:",
    ]

    result = {
        "row_col": None,
        "merge": None,
        "origin_tab": None,
    }

    try:
        part1, part2 = text.split(tags[0], 1)
        section1, part2 = part2.split(tags[1], 1)
        section2, section3 = part2.split(tags[2], 1)

        result["row_col"] = section1.strip()
        result["merge"] = section2.strip()
        result["origin_tab"] = section3.strip()

    except ValueError:
        # 任意一步失败就返回已解析的部分
        pass

    return result


def _get_TEDS(response: str, ref_ans: str) -> dict[str, float]:
    response, ref_ans = response.strip(), ref_ans.strip()

    if not response.startswith("<html>") and not response.endswith("</html>"):
        response = "<html><body>" + response + "</body></html>"
    if not ref_ans.startswith("<html>") and not ref_ans.endswith("</html>"):
        ref_ans = "<html><body>" + ref_ans + "</body></html>"

    entry: dict[str, float] = {
        "teds": teds(response, ref_ans),
        "teds_s": teds_struct(response, ref_ans),
    }
    return entry


def process_mllm_eval_task(item: dict, model_key: str) -> dict:
    """
    处理单个评测项，用于 mllm eval

    Args:
        item: 单条 infer_rst 数据，包含以下 key
            id, model_key, 参考答案
        model_key: 模型响应的键名

    Returns:
        包含评分结果的字典
    """
    item_id = item.get("id", "unknown")
    response = item.get(model_key, [""])[0] if isinstance(item.get(model_key), list) else item.get(model_key, "")
    ref_answer = item.get("参考答案", [""])[0] if isinstance(item.get("参考答案"), list) else ""

    # 初始化评分结果
    eval_score = {"teds": 0.0, "teds_s": 0.0, "error": None}

    # 标签缺失惩罚
    if not _validate_response_tags(response):
        eval_score["error"] = "Missing Tag!"
        return {"id": item_id, "eval_score": eval_score, "original": item}

    # 提取各部分
    parsed_response = _extract_by_sections(response)

    # 检查是否有最终表格结果
    if not parsed_response.get("origin_tab"):
        eval_score["error"] = "Missing origin_tab!"
        return {"id": item_id, "eval_score": eval_score, "original": item}

    # 检查是否以 </table> 结尾
    if not parsed_response["origin_tab"].endswith("</table>"):
        eval_score["error"] = "Missing Ending </table>!"
        return {"id": item_id, "eval_score": eval_score, "original": item}

    # 计算 TEDS 分数
    try:
        scores = _get_TEDS(parsed_response["origin_tab"], ref_answer)
        eval_score.update(scores)
    except Exception as e:
        eval_score["error"] = f"TEDS calculation error: {str(e)}"

    return {"id": item_id, "eval_score": eval_score, "original": item}


def process_simple_task(response: str, ref_answer: str) -> dict:
    """
    处理单个简单评测项

    Args:
        response: 模型生成的答案字符串
        ref_answer: 参考答案字符串

    Returns:
        包含评分结果的字典
    """
    return _get_TEDS(response, ref_answer)


def test_mllm_eval() -> None:
    # 测试代码
    ref = '<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>1.37</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'
    resp = '【行列数分析】:\n这是一个7行5列的表格。\n\n【合并单元格分析】:\n<merge>(1,1),(2,1)</merge><merge>(1,2),(1,3)</merge><merge>(1,4),(1,5)</merge>\n\n【最终表格解析结果】:\n<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>WORNG TEXT HERE</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'

    result = process_mllm_eval_task({"id": "test_item", "response": [resp], "参考答案": [ref]}, "response")
    print(result)


def test_simple() -> None:
    # 测试代码
    ref = '<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>1.37</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'
    resp = '<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>WORNG TEXT HERE</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'

    result = process_simple_task(resp, ref)
    print(result)


if __name__ == "__main__":
    # test_mllm_eval()
    # test_simple()
    pass
