## HTML Render service

A FastAPI + Playwright service that renders an HTML table string into a clean
PNG image. Mathematical formulas are rendered with MathJax and CJK text with a
Noto Sans CJK font. It exposes `/render/single` (one table) and `/render/dual`
(two tables side by side, used to build the VLM-judge input image).

### Environment

```bash
# Fill in your own asset paths in run.sh / demo_run.sh:
#   FONTS_DIRS          - directory of font files (*.ttc)
#   PLAYWRIGHT_BROWSERS - Playwright Chromium directory
#   MATHJAX_DIRS        - MathJax distribution directory
#   RENDER_OUTPUT_DIR   - where rendered images are written

pip install playwright fastapi uvicorn pydantic
export PLAYWRIGHT_BROWSERS_PATH="your/path/to/ms-playwright"

# Optionally install system fonts
apt-get update && apt-get install -y fonts-noto-core fonts-noto-cjk fonts-noto-mono fonts-dejavu-core
fc-cache -fv

# Single instance on one port (for debugging)
bash demo_run.sh
# Multiple local instances across a range of ports
bash run.sh
```

Register the resulting `host:port` endpoints in
`Uni_TabRL/configs/servers/html_render.json`.
