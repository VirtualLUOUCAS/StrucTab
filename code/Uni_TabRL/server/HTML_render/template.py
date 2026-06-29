EMPTY_CELL_PLACEHOLDER = "&nbsp;"

HTML_HEAD = """<head>
        <meta charset="UTF-8">
        <script>
            window.MathJax = {{
                loader: {{load: ['[tex]/extpfeil']}},
                tex: {{
                    inlineMath: [['$', '$']],
                    displayMath: [['$$', '$$']],
                    packages: {{'[+]': ['extpfeil']}}
                }},
                svg: {{
                    fontCache: 'none'
                }}
            }};
        </script>
        <script id="MathJax-script" src="{mathjax_url}"></script>

        <style>
            html {{
                background: white;
            }}
            
            body {{
                margin: 0;
                padding: 0;
            }}

            table {{
                margin: 0;
                border-collapse: collapse;
                border: 2px solid black;
            }}

            td, th {{
                border: 1px solid black;
                word-break: break-all;
                padding: 6px 12px;
            }}

            p {{
                margin: 12px 0;
                line-height: 1.5;
            }}
        </style>
    </head>
"""

SINGLE_TABLE_HTML_TEMPLATE = """
<html>
    {html_head}
    <body>
        <div style="display: inline-block; padding: {padding}px;">
            {content}
        </div>
    </body>
</html>
"""

DUAL_TABLE_HTML_TEMPLATE = """
<html>
    {html_head}
    <body>
        <div style="display: inline-flex; gap: 20px; align-items: flex-start; padding: {padding}px;">
            <div style="display: inline-block;">
                {content_left}
            </div>
            <div style="display: inline-block;">
                {content_right}
            </div>
        </div>
    </body>
</html>
"""
