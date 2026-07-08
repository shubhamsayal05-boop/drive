"""FastAPI server: serves the upload UI and the /api/analyze endpoint."""
import tempfile, os, traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .engine import analyze
from . import vehicle as vehicle_cfg
from . import edo_loader

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
CFG = Path(__file__).resolve().parent / "config"
app = FastAPI(title="DriveScope", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/api/vehicle")
def get_vehicle():
    return JSONResponse(vehicle_cfg.load())


@app.post("/api/vehicle")
async def set_vehicle(cfg: dict):
    return JSONResponse(vehicle_cfg.save(cfg))


@app.get("/api/criteria")
def get_criteria():
    try:
        crit = edo_loader.load()
        return JSONResponse({
            "source": edo_loader.active_source(),
            "n_modes": len(crit),
            "modes": list(crit.keys()),
        })
    except edo_loader.EdoParseError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/criteria")
async def upload_criteria(file: UploadFile = File(...)):
    """Upload Operation Modes Criteria (.edo or .json) from AVL-DRIVE / ODRIV."""
    data = await file.read()
    try:
        crit = edo_loader.load_from_bytes(data, source=file.filename or "upload")
        if crit.get("_avl_hierarchy"):
            avl = crit["_avl_hierarchy"]
            dest = edo_loader.import_avl_hierarchy(avl)
            n_modes = len(avl.get("modes", []))
            n_crit = sum(len(m.get("criteria", [])) for m in avl.get("modes", []))
            return JSONResponse({
                "ok": True,
                "format": "avl_hierarchy",
                "source": str(dest),
                "n_modes": n_modes,
                "n_criteria": n_crit,
            })
        dest = CFG / (file.filename if file.filename else "operation_modes_criteria.edo")
        dest.write_bytes(data)
        edo_loader.reload(dest)
        edo_loader.save_json(crit, CFG / "sdv_criteria.json")
        return JSONResponse({
            "ok": True,
            "format": "odriv_targets",
            "source": str(dest),
            "n_modes": len(crit),
            "modes": list(crit.keys()),
        })
    except edo_loader.EdoParseError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
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
