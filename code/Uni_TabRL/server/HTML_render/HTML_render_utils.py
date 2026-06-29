import os
import re

from playwright.async_api import Locator, Page
from template import DUAL_TABLE_HTML_TEMPLATE, EMPTY_CELL_PLACEHOLDER, HTML_HEAD, SINGLE_TABLE_HTML_TEMPLATE


def _sanitize_png_name(name: str) -> str:
    """
    辅助方法
    功能：防路径穿越攻击 + 自动补 .png 拓展名
    """
    # 提取文件名部分，去除路径，防路径穿越
    base = os.path.basename(name.strip())
    # 使用正则表达式替换不安全字符
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)
    if not base.lower().endswith(".png"):
        base += ".png"
    if base in {".png", ""}:
        raise ValueError("Invalid png_name")
    return base


def prepare_output_path(image_name: str, output_dir: str | None, default_output_dir: str) -> str:
    """准备输出路径"""
    sanitized_name: str = _sanitize_png_name(image_name)
    target_dir = os.path.abspath(output_dir) if output_dir else default_output_dir

    os.makedirs(target_dir, exist_ok=True)
    # 如果权限不是 777，并且没有写权限
    if oct(os.stat(target_dir).st_mode)[-3:] != "777" and not os.access(target_dir, os.W_OK):
        os.chmod(target_dir, 0o777)

    output_path = os.path.abspath(os.path.join(target_dir, sanitized_name))
    return output_path


def build_single_table_html(content: str, mathjax_url: str, padding: int) -> str:
    """构建包含 MathJax 的完整 HTML 页面"""
    html_head = HTML_HEAD.format(mathjax_url=mathjax_url)
    html = SINGLE_TABLE_HTML_TEMPLATE.format(html_head=html_head, content=content, padding=padding)
    return html


def build_dual_table_html(content_left: str, content_right: str, mathjax_url: str, padding: int) -> str:
    """构建包含两个并排表格的完整 HTML 页面"""
    html_head = HTML_HEAD.format(mathjax_url=mathjax_url)
    html = DUAL_TABLE_HTML_TEMPLATE.format(
        html_head=html_head,
        content_left=content_left,
        content_right=content_right,
        padding=padding,
    )
    return html


def fill_empty_table_cells(html: str) -> str:
    """为空的 <td></td>/<th></th> 填充占位符，避免渲染为零高度"""
    html = re.sub(r"<td>\s*</td>", f"<td>{EMPTY_CELL_PLACEHOLDER}</td>", html)
    html = re.sub(r"<th>\s*</th>", f"<th>{EMPTY_CELL_PLACEHOLDER}</th>", html)
    return html


async def _screenshot_content_area(page: Page, out_path: str, padding: int = 2) -> None:
    """
    截图内容区域（自动适配单表格或多表格布局）
    精确裁剪,去除多余空白
    """
    # 优先级：flex容器 > inline-block容器 > 表格
    selectors = [
        "body > div[style*='display: inline-flex']",  # 双表格容器
        "body > div[style*='display: inline-block']",  # 单表格容器
        "body > div:has(table)",  # 包含表格的div
        "table",  # 单个表格
    ]

    target: Locator = None
    for selector in selectors:
        target = page.locator(selector).first
        if await target.count() > 0:
            break

    if not target or await target.count() == 0:
        # 降级：截取整个页面
        await page.screenshot(path=out_path, full_page=True)
        return

    await target.wait_for(state="visible")

    # 获取元素的实际渲染边界
    box: dict[str, float] = await target.bounding_box()

    if not box:
        await page.screenshot(path=out_path, full_page=True)
        return

    # 计算截图区域（加上 padding）
    x = max(box["x"] - padding, 0)
    y = max(box["y"] - padding, 0)
    width = box["width"] + padding * 2
    height = box["height"] + padding * 2

    screen_range = {"x": x, "y": y, "width": width, "height": height}
    await page.screenshot(path=out_path, clip=screen_range)
    return


async def render_one_table(page: Page, html: str, out_path: str, padding: int) -> None:
    # 加载 HTML
    await page.set_content(html, wait_until="networkidle")

    #  等待 MathJax 渲染完成
    try:
        # 等待 MathJax 初始化
        await page.wait_for_function("window.MathJax && MathJax.startup && MathJax.startup.promise", timeout=30000)

        # 执行公式排版
        await page.evaluate("MathJax.startup.promise")
        await page.evaluate("MathJax.typesetPromise()")

        # 等待字体加载
        await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve()")

        # 再次排版（确保完整，避免字形错误）
        await page.evaluate("MathJax.typesetPromise()")
    except Exception:
        pass

    # 截图内容区域
    await _screenshot_content_area(page, out_path, padding=padding)
    return
