"""Bridge DriveScope's signal-derived events to the official ODRIV SDV taxonomy
and build an ODRIV-style criteria scorecard (criterion / target / warn-limit /
measured rating / verdict) per event, using Operation Modes Criteria (.edo)."""
import json
from pathlib import Path

from . import edo_loader
from . import criteria as crit_mod

CFG = Path(__file__).parent / "config"
_CATALOG = json.loads((CFG / "sdv_catalog.json").read_text(encoding="utf-8"))
_GROUP = {c["name"]: c["group"] for c in _CATALOG}

SDV_FOR_TYPE = {
    "drive_away": "Drive Away Creep Eng On",
    "drive_away_ess": "DASS Eng Off quick",
    "accel_constant_load": "Accel Cst Load",
    "accel_load_increase": "Accel Load Increase",
    "poweron_upshift": "Power-on upshift",
    "kickdown_downshift": "(PT) KD - tip in downshift",
    "tip_out_overrun": "Tip Out After Acceleration",
    "lever_change": "Lever change",
    "tip_in_cstspd": "Tip in at constant speed",
    "tip_out_cstspd": "Tip Out At Constant Speed",
    "decel_coast": "Decel Without Brake",
    "decel_brake": "Decel Cst Brake",
    "engine_start": "Manual Start",
    "engine_stop": "Manual Stop",
    "idle": "Idle Vehicle Stationary",
}


def sdv_for(ev):
    name = SDV_FOR_TYPE.get(ev["type"], ev.get("label", ev["type"]))
    return name, _GROUP.get(name, "")


def scorecard(ev, m, issues=None):
    """Return (sdv_name, group, criteria_rows) with ODRIV ratings from .edo targets."""
    name, group = sdv_for(ev)
    db = edo_loader.load()
    rows = crit_mod.evaluate_mode(name, m, db)
    # enrich measured display: show rating + physical when both exist
    for r in rows:
        if r["rating"] is not None and r.get("physical") is not None:
            r["measured"] = f"{r['rating']:.1f} ({r['physical']} {r['unit']})"
        elif r["rating"] is not None:
            r["measured"] = f"{r['rating']:.1f}"
    return name, group, rows


def catalog():
    return _CATALOG


def criteria_source():
    return edo_loader.active_source()
