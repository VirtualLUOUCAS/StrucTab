import os
import sys
from argparse import ArgumentParser

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.ping_service_base import ServiceTester

"""
TEDS Judger 服务测试脚本
使用方式：python ping_TEDS_judger.py --input {服务器列表 JSON 路径}
"""

DEFAULT_INPUT_JSON_PATH = "your/path/to/endpoints.json"  # 端点列表 JSON 路径 (格式: ["ip:port", ...])


class TEDSJudgerTester(ServiceTester):
    """TEDS Judger 测试器"""

    def __init__(self):
        super().__init__(
            service_name="TEDS_judger",
            start_port=18910,
            end_port=18939,
            router="/judge/mllm_eval",
            request_timeout=20,
        )

    def get_test_data(self) -> dict:
        return {
            "item": {
                "response": [
                    '【行列数分析】:\n这是一个7行5列的表格。\n\n【合并单元格分析】:\n<merge>(1,1),(2,1)</merge><merge>(1,2),(1,3)</merge><merge>(1,4),(1,5)</merge>\n\n【最终表格解析结果】:\n<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>WORNG TEXT HERE</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'
                ],
                "参考答案": [
                    '<table><tr><td rowspan="2">R</td><td colspan="2">C = 4π</td><td colspan="2">C = -4π</td></tr><tr><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td><td>$r_{\\lambda }$</td><td>$r_{\\Lambda }$</td></tr><tr><td>2</td><td>0.34</td><td>0.26</td><td>1.66</td><td>1.32</td></tr><tr><td>e</td><td>0.48</td><td>0.34</td><td>1.52</td><td>1.41</td></tr><tr><td>5</td><td>0.75</td><td>0.59</td><td>1.25</td><td>1.37</td></tr><tr><td>7</td><td>0.85</td><td>0.71</td><td>1.15</td><td>1.29</td></tr><tr><td>10</td><td>0.91</td><td>0.80</td><td>1.09</td><td>1.20</td></tr></table>'
                ],
            },
            "model_key": "response",
        }

    def check_response_validity(self, response: dict) -> bool:
        required_keys = {"id", "eval_score", "original"}
        if not all(key in response for key in required_keys):
            return False
        if not isinstance(response["id"], (int, str)):
            return False
        if not isinstance(response["eval_score"], dict):
            return False
        if not isinstance(response["original"], dict):
            return False
        return True

    def get_success_message(self, response: dict) -> str:
        return f"✅ 成功，得分: {response['eval_score']}"


if __name__ == "__main__":
    parser = ArgumentParser(description="测试 TEDS Judger 服务端点")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT_JSON_PATH, help="服务器列表 JSON 路径")
    args = parser.parse_args()

    tester = TEDSJudgerTester()
    tester.test_all_servers(args.input)
