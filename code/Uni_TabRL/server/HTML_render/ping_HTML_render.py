import sys
from argparse import ArgumentParser
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.ping_service_base import ServiceTester

"""
HTML Render 服务测试脚本
使用方式：python ping_HTML_render.py --input {服务器列表 JSON 路径}
"""

DEFAULT_INPUT_JSON_PATH = "your/path/to/endpoints.json"  # 端点列表 JSON 路径 (格式: ["ip:port", ...])


class HTMLRenderTester(ServiceTester):
    """HTML Render 测试器"""

    def __init__(self):
        super().__init__(
            service_name="HTML_render",
            start_port=18940,
            end_port=18969,
            router="/render",
            request_timeout=20,
        )

    def get_test_data(self) -> dict:
        return {
            "content": "<table><tr><td>1.肉</td><td>点</td><td>6.绿黄色野菜</td><td>点</td></tr><tr><td>2.鱼介類</td><td>点</td><td>7.海藻類</td><td>点</td></tr><tr><td>3.卵</td><td>点</td><td>8.いも</td><td>点</td></tr><tr><td>4.大豆·大豆製品</td><td>点</td><td>9.果物</td><td>点</td></tr><tr><td>5.牛乳·乳製>品</td><td>点</td><td>10.油を使った料理</td><td>点</td></tr><tr><td>あなたの点数は？</td><td>...</td><td>→</td><td>点</td></tr></table>",
            "image_name": "py_test.png",
        }

    def check_response_validity(self, response: dict) -> bool:
        required_keys = {"image_path"}
        if not all(key in response for key in required_keys):
            return False
        if not isinstance(response["image_path"], str):
            return False
        return True


if __name__ == "__main__":
    parser = ArgumentParser(description="测试 HTML Render 服务端点")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT_JSON_PATH, help="服务器列表 JSON 路径")
    args = parser.parse_args()

    tester = HTMLRenderTester()
    tester.test_all_servers(args.input)
