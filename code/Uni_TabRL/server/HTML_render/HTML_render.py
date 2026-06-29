import asyncio
import gc
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from HTML_render_utils import (
    build_dual_table_html,
    build_single_table_html,
    fill_empty_table_cells,
    prepare_output_path,
    render_one_table,
)
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from pydantic import BaseModel, Field

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("HTML_render")

#! Config
OUT_DIR = os.path.abspath(os.getenv("OUT_DIR", "Render_output"))  # 输出目录
TABLE_PADDING = int(os.getenv("TABLE_PADDING", "6"))  # 表格截图 padding
RENDER_CONCURRENCY = int(os.getenv("RENDER_CONCURRENCY", "4"))  # 并发渲染数
VIEWPORT_W = int(os.getenv("VIEWPORT_W", "2000"))  # 浏览器视窗宽度
VIEWPORT_H = int(os.getenv("VIEWPORT_H", "2000"))  # 浏览器视窗高度
DEVICE_SCALE_FACTOR = float(os.getenv("DEVICE_SCALE_FACTOR", "2"))  # 设备像素比

# 设置 MATHJAX_DIR 环境变量
MATHJAX_DIR = os.getenv("MATHJAX_DIR")
assert MATHJAX_DIR, "MATHJAX_DIR environment variable is not set"
assert os.path.isdir(MATHJAX_DIR), f"MATHJAX_DIR does not exist or is not a directory: {MATHJAX_DIR}"

MATHJAX_ES5_DIR = os.path.join(MATHJAX_DIR, "es5")
MATHJAX_MAIN_FILE = "tex-svg.js"

#! Globals
_playwright = None
_browser: Optional[Browser] = None
_browser_context: Optional[BrowserContext] = None
_render_sem = asyncio.Semaphore(RENDER_CONCURRENCY)


async def refresh_browser_context():
    """刷新浏览器上下文以释放内存"""
    global _browser_context

    if _browser_context:
        try:
            await _browser_context.close()
            logger.info("Closed old browser context")
        except Exception as e:
            logger.warning(f"Error closing old context: {e}")

    # 创建可复用的 context
    _browser_context = await _browser.new_context(
        viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
        device_scale_factor=DEVICE_SCALE_FACTOR,
    )
    logger.info("Created new browser context")

    # 强制垃圾回收
    gc.collect()


#! FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 启动 Playwright 浏览器
    global _playwright, _browser, _browser_context
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        # 如果权限不是 777，并且没有写权限
        if oct(os.stat(OUT_DIR).st_mode)[-3:] != "777" and not os.access(OUT_DIR, os.W_OK):
            os.chmod(OUT_DIR, 0o777)
    except Exception as e:
        logger.error(f"Failed to create or set permissions for OUT_DIR '{OUT_DIR}': {e}")
        raise

    logger.info("Starting browser...")
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        chromium_sandbox=True,
        args=[
            "--disable-dev-shm-usage",  # 避免共享内存问题
            "--disable-gpu",
        ],
    )

    await refresh_browser_context()
    logger.info("Browser initialized")

    yield

    # Shutdown: 清理资源
    logger.info("Shutting down browser...")
    try:
        if _browser_context:
            await _browser_context.close()
        if _browser:
            await _browser.close()
        if _playwright:
            await _playwright.stop()
    finally:
        logger.info("Browser shut down")
        _browser_context = None
        _browser = None
        _playwright = None
        gc.collect()
    return


app = FastAPI(title="Table-only HTML-to-PNG Renderer (MathJax + Playwright)", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=MATHJAX_ES5_DIR), name="static")


class BaseRenderRequest(BaseModel):
    image_name: str = Field(..., description="output file name, e.g. 123.png or 123")
    output_dir: Optional[str] = Field(None, description="override output directory for this request")
    padding: Optional[int] = Field(None, description="override padding for this request")


class SingleRenderRequest(BaseRenderRequest):
    content: str = Field(..., description="HTML fragment containing the <table> to render")


class DualRenderRequest(BaseRenderRequest):
    content_left: str = Field(..., description="HTML fragment for left table")
    content_right: str = Field(..., description="HTML fragment for right table")


class RenderResponse(BaseModel):
    image_path: str


# ============ Helper Functions ============
def get_mathjax_url(request: Request) -> str:
    """获取 MathJax URL"""  # 获取请求的端口号
    port = request.url.port or 80
    mathjax_url = f"http://127.0.0.1:{port}/static/{MATHJAX_MAIN_FILE}"
    # print(f"Using MathJax URL: {mathjax_url}")
    return mathjax_url


async def render_html_to_png(html: str, out_path: str, padding: int) -> None:
    """渲染 HTML 到 PNG (通用渲染逻辑)"""
    if _browser_context is None:
        raise HTTPException(status_code=503, detail="Browser not ready")

    async with _render_sem:  # 信号量限制并发
        page: Page = None
        try:
            page = await _browser_context.new_page()
            await render_one_table(page, html, out_path, padding=padding)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Render timeout exceeded")
        except Exception as e:
            logger.error(f"Render error: {e}")
            raise
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")
                finally:
                    page = None
    return


# ============ Routes ============
@app.get("/health")
async def health():
    if _browser is None or _browser_context is None:
        return {"status": "error", "detail": "Browser not ready"}
    return {"status": "ok"}


@app.post("/render/single", response_model=RenderResponse)
async def render_single(req: SingleRenderRequest, request: Request) -> RenderResponse:
    """渲染单个表格"""
    try:
        out_path = prepare_output_path(req.image_name, req.output_dir, OUT_DIR)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    padding = req.padding if req.padding is not None else TABLE_PADDING
    mathjax_url = get_mathjax_url(request)

    # 填充空单元格并构建 HTML
    content = fill_empty_table_cells(req.content)
    html = build_single_table_html(content, mathjax_url, padding)

    await render_html_to_png(html, out_path, padding)
    return RenderResponse(image_path=out_path)


@app.post("/render", response_model=RenderResponse)
async def render_legacy(req: SingleRenderRequest, request: Request) -> RenderResponse:
    """渲染单个表格 (兼容旧版 API)"""
    return await render_single(req, request)


@app.post("/render/dual", response_model=RenderResponse)
async def render_dual(req: DualRenderRequest, request: Request) -> RenderResponse:
    """渲染两个并排表格"""
    try:
        out_path = prepare_output_path(req.image_name, req.output_dir, OUT_DIR)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    padding = req.padding if req.padding is not None else TABLE_PADDING
    mathjax_url = get_mathjax_url(request)

    # 填充空单元格并构建 HTML
    content_left = fill_empty_table_cells(req.content_left)
    content_right = fill_empty_table_cells(req.content_right)
    html = build_dual_table_html(content_left, content_right, mathjax_url, padding)

    await render_html_to_png(html, out_path, padding)
    return RenderResponse(image_path=out_path)
