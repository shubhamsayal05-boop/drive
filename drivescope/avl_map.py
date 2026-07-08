"""Map DriveScope detected events to AVL-DRIVE Operation modes (Main / Sub).

AVL taxonomy: Main operation mode → Sub operation mode → Criterion (enabled).
Targets (t / wl) are resolved from sdv_criteria.json via an ODRIV SDV crosswalk.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import criteria as crit_mod
from . import edo_loader

CFG = Path(__file__).parent / "config"
_AVL = json.loads((CFG / "avl_operation_modes.json").read_text(encoding="utf-8"))
_SDV_TARGETS = json.loads((CFG / "sdv_criteria.json").read_text(encoding="utf-8"))

# DriveScope event type -> (main, sub) in AVL Operation modes / Criteria UI
AVL_FOR_TYPE = {
    "drive_away": ("Drive away", "Standing start"),
    "drive_away_ess": ("Drive away", "Creep"),
    "accel_constant_load": ("Acceleration", "Constant load"),
    "accel_load_increase": ("Acceleration", "Load increase"),
    "poweron_upshift": ("Gear shift", "Power-on upshift"),
    "kickdown_downshift": ("Gear shift", "Kick down / tip in downshift"),
    "tip_out_overrun": ("Deceleration", "Coast down"),
    "lever_change": ("Gear shift", "Selector lever change"),
    "tip_in_cstspd": ("Tip in", "At constant speed / acceleration"),
    "tip_out_cstspd": ("Tip out", "At constant speed / acceleration"),
    "tip_out_overrun": ("Tip out", "At deceleration"),
    "decel_coast": ("Deceleration", "Without brake"),
    "decel_brake": ("Deceleration", "Constant Brake"),
    "engine_start": ("Engine start", "Manual start"),
    "engine_stop": ("Engine shut off", "Manual stop"),
    "idle": ("Idle", "Vehicle stationary"),
}

# (main, sub) -> ODRIV SDV name for target lookup in sdv_criteria.json
SDV_CROSSWALK = {
    ("Drive away", "Creep"): "Drive Away Creep Eng On",
    ("Drive away", "Standing start"): "Drive Away Creep Eng On",
    ("Drive away", "Hill start"): "Drive Away Hill Start",
    ("Drive away", "Rolling start"): "DA Rolling Start",
    ("Acceleration", "Constant load"): "Accel Cst Load",
    ("Acceleration", "Load increase"): "Accel Load Increase",
    ("Acceleration", "Load decrease"): "Accel Load Decrease",
    ("Deceleration", "Without brake"): "Decel Without Brake",
    ("Deceleration", "Constant Brake"): "Decel Cst Brake",
    ("Deceleration", "Coast down"): "Tip Out After Acceleration",
    ("Gear shift", "Power-on upshift"): "Power-on upshift",
    ("Gear shift", "Power-on downshift"): "Power-on downshift",
    ("Gear shift", "Kick down / tip in downshift"): "(PT) KD - tip in downshift",
    ("Gear shift", "Tip-in downshift"): "(PT) KD - tip in downshift",
    ("Gear shift", "Tip-in at constant speed"): "Tip in at constant speed",
    ("Gear shift", "Tip in upshift"): "Tip out upshift",
    ("Gear shift", "Tip-out upshift"): "Tip out upshift",
    ("Gear shift", "Coast / brake-on downshift"): "Coast - brake-on downshift",
    ("Gear shift", "Coast / brake-on upshift"): "Coast - brake-on upshift",
    ("Gear shift", "Load reversal downshift"): "Load Reversal Downshift",
    ("Gear shift", "Load reversal upshift"): "Load Reversal upshift",
    ("Gear shift", "Selector lever change"): "Lever change",
    ("Gear shift", "Maneuvering"): "Maneuvering",
    ("Gear shift", "Shift abort"): "Shift Abort",
    ("Engine start", "Manual start"): "Manual Start",
    ("Engine shut off", "Manual stop"): "Manual Stop",
    ("Constant speed", "Without load"): "Idle Vehicle Stationary",
    ("Idle", "Vehicle stationary"): "Idle Vehicle Stationary",
    ("Tip in", "At constant speed / acceleration"): "Tip in at constant speed",
    ("Tip in", "At deceleration"): "Tip in at deceleration",
    ("Tip out", "At constant speed / acceleration"): "Tip Out At Constant Speed",
    ("Tip out", "At deceleration"): "Tip Out After Acceleration",
    ("TCC control", "Converter controlled slip"): "Converter controlled slip",
    ("TCC control", "Converter lock up"): "Converter lock up",
    ("TCC control", "Converter release"): "Converter release",
    ("Sailing", "Enter sailing"): "Sailing Enter",
    ("Sailing", "Exit sailing"): "Sailing Exit",
    ("Gear shift", "Tip out downshift"): "(TO) KD - tip in downshift",
    ("Gear shift", "Upshift"): "Power-on upshift",
    ("Vehicle stationary", "Vehicle stop"): "Vehicle Stop",
}


def _mode_index():
    idx = {}
    for m in _AVL.get("modes", []):
        idx[(m["main"], m["sub"])] = m
    return idx


_MODE_IDX = _mode_index()


def avl_for(ev: dict) -> tuple[str, str]:
    return AVL_FOR_TYPE.get(ev["type"], ("Unknown", ev.get("label", ev["type"])))


def _targets_for(main: str, sub: str) -> dict[str, dict]:
    """Criterion name -> {t, wl, driv} from ODRIV targets file."""
    sdv = SDV_CROSSWALK.get((main, sub))
    if not sdv:
        return {}
    out = {}
    for row in _SDV_TARGETS.get(sdv, []):
        out[row["criteria"]] = row
    return out


def enabled_criteria(main: str, sub: str) -> list[dict]:
    m = _MODE_IDX.get((main, sub))
    if not m:
        return []
    return [c for c in m.get("criteria", []) if c.get("enabled", True)]


def scorecard(ev: dict, metrics: dict) -> tuple[str, str, str, list[dict]]:
    """Return (main, sub, sdv_name, criteria_rows) using AVL hierarchy + ODRIV targets."""
    main, sub = avl_for(ev)
    sdv = SDV_CROSSWALK.get((main, sub), "")
    targets = _targets_for(main, sub)
    enabled = enabled_criteria(main, sub)

    rows = []
    for i, c in enumerate(enabled):
        name = c["name"]
        tgt = targets.get(name, {})
        t = float(tgt.get("t", 7.0))
        wl = float(tgt.get("wl", 6.0))
        driv = int(tgt.get("driv", i + 1))
        phys, unit, rating = crit_mod.rate_criterion(name, metrics)
        sev = crit_mod.verdict_for_rating(rating, t, wl)
        measured = None
        if rating is not None and phys is not None:
            measured = f"{rating:.1f} ({phys} {unit})"
        elif rating is not None:
            measured = f"{rating:.1f}"
        elif phys is not None:
            measured = f"{phys} {unit}"
        rows.append({
            "main": main,
            "sub": sub,
            "criteria": name,
            "enabled": True,
            "t": t,
            "wl": wl,
            "driv": driv,
            "physical": phys,
            "unit": unit,
            "rating": rating,
            "measured": measured,
            "sev": sev if rating is not None else "na",
        })

    rows.sort(key=lambda r: (r["rating"] is None, r.get("driv") or 9))
    return main, sub, sdv, rows


def catalog():
    return _AVL


def reload_catalog():
    global _AVL, _MODE_IDX, _SDV_TARGETS
    _AVL = json.loads((CFG / "avl_operation_modes.json").read_text(encoding="utf-8"))
    _MODE_IDX = _mode_index()
    _SDV_TARGETS = json.loads((CFG / "sdv_criteria.json").read_text(encoding="utf-8"))
