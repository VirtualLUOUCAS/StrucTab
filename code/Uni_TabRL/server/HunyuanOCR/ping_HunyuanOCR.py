# -*- coding: utf-8 -*-
import base64
import json
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

from openai import OpenAI

"""
用于测试多个 HunyuanOCR 服务端点的可用性脚本。
使用方式：命令行运行
python ping_HunyuanOCR.py --input {端点列表 JSON 路径} --test_image {测试图片路径}
"""

# 配置基础信息
INPUT_JSON_PATH = "your/path/to/endpoints.json"  # 端点列表 JSON 路径 (格式: ["ip:port", ...])
TEST_IMAGE_PATH = "HunyuanOCR/test/test_image.png"  # 默认测试图片路径

WORKERS = 50  # 并行工作线程数
REQUEST_TIMEOUT = 30  # 请求超时时间（秒）

# 固定测试数据
DEFAULT_QUESTION = "把图中的表格解析为HTML。"
DEFAULT_SYSTEM_PROMPT = ""

# 输出文件路径
OUTPUT_DIR = Path("server_results/HunyuanOCR")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.chmod(0o777)

# 用于线程安全的打印和计数
print_lock = Lock()


def encode_base64(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_messages(image_path: str, question: str, system_prompt: str = "") -> list[dict]:
    """构造适合 vLLM API 的消息格式"""
    messages = [
        {"role": "system", "content": system_prompt if system_prompt else ""},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_base64(image_path)}"}},
                {"type": "text", "text": question},
            ],
        },
    ]
    return messages


def check_response_validity(response: str) -> bool:
    """
    检查返回的响应是否有效

    :param response: 返回的文本响应
    :return: 是否有效
    """
    # 基本检查：响应不为空，且包含一定长度的内容
    if not response or len(response.strip()) < 10:
        return False

    # 可以添加更多验证逻辑，例如检查是否包含 HTML 标签
    return True


def load_endpoints(json_path: str) -> list[str]:
    """
    从 JSON 文件加载端点列表

    :param json_path: JSON 文件路径
    :return: 端点列表 (ip:port 格式)
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            print("JSON 文件为空")
            return []

        # 检查格式
        if not all(":" in item for item in data):
            print("错误：JSON 文件中的端点格式不正确，应为 'ip:port' 格式")
            return []

        print(f"成功加载 {len(data)} 个端点\n")
        return data

    except Exception as e:
        print(f"加载 JSON 文件失败: {e}")
        return []


def test_single_endpoint(
    endpoint: str, test_image: str, model_name: str = "HYVL", silent: bool = False
) -> tuple[str, bool, str]:
    """
    测试单个端点的可用性

    :param endpoint: 端点 (ip:port 格式)
    :param test_image: 测试图片路径
    :param model_name: 模型名称
    :param silent: 是否静默模式（不打印详细信息）
    :return: (endpoint, is_available, error_message)
    """
    if not silent:
        with print_lock:
            print(f"测试 {endpoint} ...", end=" ", flush=True)

    try:
        # 构建客户端
        client = OpenAI(
            base_url=f"http://{endpoint}/v1",
            api_key="EMPTY",
            timeout=REQUEST_TIMEOUT,
        )

        # 构建消息
        messages = build_messages(test_image, DEFAULT_QUESTION, DEFAULT_SYSTEM_PROMPT)

        # 调用 API
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0,
            stream=False,
        )

        # 获取响应
        output_str = completion.choices[0].message.content

        # 验证响应
        if check_response_validity(output_str):
            if not silent:
                with print_lock:
                    print(f"✅ 成功：{output_str[:50]}...", flush=True)
            return endpoint, True, ""
        else:
            if not silent:
                with print_lock:
                    print("❌ 响应内容无效", flush=True)
            return endpoint, False, "Invalid response content"

    except Exception as e:
        error_msg = str(e)
        if "timeout" in error_msg.lower():
            error_type = "超时"
        elif "connection" in error_msg.lower():
            error_type = "无法连接"
        else:
            error_type = f"异常: {error_msg[:50]}"

        if not silent:
            with print_lock:
                print(f"❌ {error_type}", flush=True)

        return endpoint, False, error_msg


def test_endpoints_parallel(
    endpoints: list[str], test_image: str, model_name: str = "HYVL"
) -> tuple[list[str], list[dict]]:
    """
    并行测试给定的端点列表

    :param endpoints: 端点列表 (ip:port 格式)
    :param test_image: 测试图片路径
    :param model_name: 模型名称
    :return: (available_endpoints, unavailable_endpoints_with_errors)
    """
    available = []
    unavailable = []

    print(f"\n开始并行测试 {len(endpoints)} 个端点")
    print(f"测试图片: {test_image}")
    print(f"模型名称: {model_name}")
    print(f"并行线程数: {WORKERS}")
    print("-" * 60)

    # 使用线程池并行测试所有端点
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        # 提交所有任务
        future_to_endpoint = {
            executor.submit(test_single_endpoint, endpoint, test_image, model_name): endpoint for endpoint in endpoints
        }

        # 收集结果
        completed = 0
        for future in as_completed(future_to_endpoint):
            completed += 1
            try:
                endpoint, is_available, error_msg = future.result()

                if is_available:
                    available.append(endpoint)
                else:
                    unavailable.append({"endpoint": endpoint, "error": error_msg})

                # 每完成 10 个显示一次进度
                if completed % 10 == 0:
                    with print_lock:
                        print(
                            f"进度: {completed}/{len(endpoints)} "
                            f"({completed / len(endpoints) * 100:.1f}%) | "
                            f"可用: {len(available)}"
                        )

            except Exception as e:
                endpoint = future_to_endpoint[future]
                with print_lock:
                    print(f"测试 {endpoint} 时发生异常: {e}")
                unavailable.append({"endpoint": endpoint, "error": f"Exception: {str(e)}"})

    with print_lock:
        print(f"\n所有端点测试完成：可用 {len(available)}/{len(endpoints)} 个端点")

    return available, unavailable


def test_all_endpoints(endpoints_path: str, test_image: str, model_name: str = "HYVL"):
    """
    测试所有端点，并保存结果

    :param endpoints_path: 端点列表 JSON 文件路径
    :param test_image: 测试图片路径
    :param model_name: 模型名称
    """
    # 验证测试图片
    if not Path(test_image).exists():
        print(f"错误：测试图片不存在: {test_image}")
        return

    # 加载端点数据
    endpoints = load_endpoints(endpoints_path)
    if not endpoints:
        print("没有可测试的端点")
        return

    print("=" * 60)
    print(f"开始测试 {len(endpoints)} 个预定义端点")

    # 并行测试所有端点
    available_endpoints, unavailable_endpoints = test_endpoints_parallel(endpoints, test_image, model_name)

    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    available_json = OUTPUT_DIR / f"available_endpoints_{timestamp}.json"
    unavailable_json = OUTPUT_DIR / f"unavailable_endpoints_{timestamp}.json"

    # 保存 JSON 格式
    with open(available_json, "w", encoding="utf-8") as f:
        json.dump(available_endpoints, f, indent=2, ensure_ascii=False)

    with open(unavailable_json, "w", encoding="utf-8") as f:
        json.dump(unavailable_endpoints, f, indent=2, ensure_ascii=False)

    # 打印统计信息
    print("\n" + "=" * 60)
    print("测试完成！统计信息：")
    print("=" * 60)
    print(f"总测试端点数: {len(endpoints)}")
    print(f"可用端点数: {len(available_endpoints)} ({len(available_endpoints) / len(endpoints) * 100:.1f}%)")
    print(f"不可用端点数: {len(unavailable_endpoints)} ({len(unavailable_endpoints) / len(endpoints) * 100:.1f}%)")
    print("\n结果文件保存位置:")
    print(f"  可用端点 (JSON): {available_json.absolute()}")
    print(f"  不可用端点 (JSON): {unavailable_json.absolute()}")

    # 显示部分错误信息（如果有）
    if unavailable_endpoints:
        print("\n前 5 个错误示例:")
        for item in unavailable_endpoints[:5]:
            print(f"  {item['endpoint']}: {item['error'][:100]}")


if __name__ == "__main__":
    parser = ArgumentParser(description="测试 HunyuanOCR 服务端点可用性")
    parser.add_argument(
        "--input", type=str, default=INPUT_JSON_PATH, help="端点列表 JSON 路径 (格式: ['ip:port', ...])"
    )
    parser.add_argument("--test_image", type=str, default=TEST_IMAGE_PATH, help="用于测试的图片路径")
    parser.add_argument("--model_name", type=str, default="HYVL", help="模型名称")
    parser.add_argument("--workers", type=int, default=WORKERS, help="并行工作线程数")

    args = parser.parse_args()

    # 更新全局变量
    WORKERS = args.workers

    test_all_endpoints(args.input, args.test_image, args.model_name)
