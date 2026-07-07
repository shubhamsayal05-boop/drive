"""Render a standalone, offline HTML report (CLI output).

Inlines the shared CSS + renderer (app.js) and the engine result, so the file
opens anywhere with no server. Same renderer as the web app -> identical look.
"""
import json
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def render_html(result: dict) -> str:
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    appjs = (FRONTEND / "app.js").read_text(encoding="utf-8")
    data = json.dumps(result, separators=(",", ":"))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;680;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<title>DriveScope — {Path(result['file']).name}</title><style>{css}</style></head>
<body><div id="app" class="ds-app"></div>
<script>{appjs}</script>
<script>DriveScope.renderApp(document.getElementById("app"), {data});</script>
</body></html>"""


def write_report(result: dict, out_path):
    Path(out_path).write_text(render_html(result), encoding="utf-8")
    return out_path
