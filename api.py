"""FastAPI server: serves the upload UI and the /api/analyze endpoint."""
import tempfile, os, traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .engine import analyze
from . import vehicle as vehicle_cfg

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app = FastAPI(title="DriveScope", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/api/vehicle")
def get_vehicle():
    return JSONResponse(vehicle_cfg.load())


@app.post("/api/vehicle")
async def set_vehicle(cfg: dict):
    return JSONResponse(vehicle_cfg.save(cfg))


@app.get("/", response_class=HTMLResponse)
def index():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    # inline assets so the whole page is a single UTF-8 document (avoids static
    # files being served without charset=utf-8 on some platforms -> mojibake).
    html = html.replace('<link rel="stylesheet" href="/static/styles.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="/static/app.js"></script>', f"<script>\n{js}\n</script>")
    return HTMLResponse(html, media_type="text/html; charset=utf-8")


@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename or "")[1] or ".dat"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read()); tmp.flush(); tmp.close()
        result = analyze(tmp.name)
        result["file"] = file.filename or result["file"]
        return JSONResponse(result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=f"Could not analyze file: {e}")
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass
