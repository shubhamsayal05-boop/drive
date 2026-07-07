"""Bridge DriveScope's signal-derived events to the official ODRIV SDV taxonomy
and build an ODRIV-style criteria scorecard (criterion / target / warn-limit /
measured / verdict) per event, using the program's own targets.

The SDV catalog and per-SDV criteria+targets are loaded from config files that
mirror the ODRIV tool (catalog.json -> sdv_catalog.json, targets.json ->
sdv_criteria.json). This keeps DriveScope aligned with ODRIV's vocabulary.
"""
import json
from pathlib import Path

CFG = Path(__file__).parent / "config"
_CATALOG = json.loads((CFG / "sdv_catalog.json").read_text(encoding="utf-8"))
_CRITERIA = json.loads((CFG / "sdv_criteria.json").read_text(encoding="utf-8"))
_GROUP = {c["name"]: c["group"] for c in _CATALOG}

# DriveScope detector type -> official SDV name (engine-on default; ESS handled below)
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

# ODRIV criterion name -> how to fill its "measured" cell from DriveScope metrics.
# (value is a PHYSICAL measurement, not the AVL 0-10 rating; shown alongside the
#  official target/warn ratings for orientation.)
def _measured_map(m):
    g = lambda k: m.get(k)
    out = {}
    def put(crit, val, unit, keys):
        if val is None:
            return
        if unit == "ms" and val < 0:        # negative latency is meaningless here
            return
        out[crit] = {"value": val, "unit": unit, "keys": keys}
    put("Shock", g("shock"), "m/s²", ["shock"])
    put("Ax gradients during ratio change", g("posg"), "m/s²/s", ["posg"])
    put("Ax gradients after ratio change", g("negg"), "m/s²/s", ["negg"])
    put("Response delay", g("tot_ms") or g("launch_ms"), "ms", ["tot_ms", "launch_ms"])
    put("Ax build-up delay", g("tot_ms"), "ms", ["tot_ms"])
    put("Ax increase delay", g("tot_ms"), "ms", ["tot_ms"])
    put("Shift delay", g("dec_ms"), "ms", ["dec_ms"])
    put("Shift duration", g("exec_ms"), "ms", ["exec_ms"])
    put("Acceleration disturbances", g("disturb_pp"), "m/s²", ["disturb_pp"])
    put("Acceleration disturbances LF", g("disturb_pp"), "m/s²", ["disturb_pp"])
    put("Surge", g("negg") if g("negg") is not None else g("disturb_pp"), "m/s²/s", ["negg"])
    put("Steadiness", g("linearity_pct"), "%", ["linearity_pct"])
    put("Jerks", g("jerk_peak") or g("jerk_rms"), "m/s²/s", ["jerk_peak", "jerk_rms"])
    put("Engine speed at engagement", g("rpm_start"), "rpm", ["rpm_start"])
    put("Expected acceleration", g("ax_mean") or g("ax_peak"), "m/s²", ["ax_mean", "ax_peak"])
    put("Reference acceleration", g("ax_peak"), "m/s²", ["ax_peak"])
    put("Engagement shock", g("jerk_peak"), "m/s²/s", ["jerk_peak"])
    put("Initial Bump", g("posg"), "m/s²/s", ["posg"])
    return out


def sdv_for(ev):
    name = SDV_FOR_TYPE.get(ev["type"], ev.get("label", ev["type"]))
    return name, _GROUP.get(name, "")


def scorecard(ev, m, issues):
    """Return (sdv_name, group, criteria_rows). Each row:
       {criteria, t, wl, driv, measured, unit, sev}."""
    name, group = sdv_for(ev)
    crit_list = _CRITERIA.get(name, [])
    meas = _measured_map(m)
    # map issue severities onto criteria by keyword for a verdict on measured rows
    def sev_for(crit):
        title = crit.lower()
        for i in issues:
            t = i["title"].lower()
            if any(w in title for w in t.split()) or any(w in t for w in title.split()):
                return i["severity"]
        return "meas"
    rows = []
    for c in crit_list:
        mc = meas.get(c["criteria"])
        rows.append({
            "criteria": c["criteria"], "t": c.get("t"), "wl": c.get("wl"), "driv": c.get("driv"),
            "measured": (f"{mc['value']} {mc['unit']}" if mc else None),
            "sev": (sev_for(c["criteria"]) if mc else "na"),
        })
    # measured criteria first, then the rest (by ODRIV driv priority already sorted)
    rows.sort(key=lambda r: (r["measured"] is None, r.get("driv") or 9))
    return name, group, rows


def catalog():
    return _CATALOG
