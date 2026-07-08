"""Operation-mode criteria evaluation: physical metrics -> AVL 0–10 ratings -> verdicts.

Uses targets from ``edo_loader`` (``.edo`` / ``sdv_criteria.json``) per SDV / operation mode.
"""
from __future__ import annotations

from . import edo_loader

# Criterion -> (metric keys, unit, higher_is_better, anchor pairs [(physical, rating)])
# Anchors are approximate ODRIV/AVL rating curves for triage — not certified AVL ratings.
ANCHORS = {
    "Response delay": (["tot_ms", "launch_ms", "resp_ms"], "ms", False,
                       [(150, 10), (300, 8), (450, 6.5), (600, 5), (900, 2), (1200, 0)]),
    "Ax build-up delay": (["tot_ms", "resp_ms"], "ms", False,
                          [(150, 10), (300, 8), (500, 6), (800, 3), (1200, 0)]),
    "Ax increase delay": (["tot_ms", "resp_ms"], "ms", False,
                          [(150, 10), (300, 8), (500, 6), (800, 3), (1200, 0)]),
    "Shift delay": (["dec_ms"], "ms", False,
                    [(80, 10), (150, 8), (250, 6), (400, 4), (700, 0)]),
    "Shift duration": (["exec_ms"], "ms", False,
                       [(200, 10), (350, 8), (500, 6), (700, 4), (1000, 0)]),
    "Duration": (["exec_ms", "start_ms", "restart_ms"], "ms", False,
                 [(300, 10), (500, 8), (800, 6), (1200, 3), (2000, 0)]),
    "Delay": (["tot_ms", "launch_ms", "resp_ms"], "ms", False,
              [(150, 10), (300, 8), (500, 6), (800, 3), (1200, 0)]),
    "Shock": (["shock", "ax_pp"], "m/s²", False,
              [(0.3, 10), (0.6, 8), (1.0, 6), (1.5, 4), (2.5, 0)]),
    "Kick": (["posg"], "m/s²/s", False,
             [(12, 10), (20, 8), (30, 6), (45, 3), (70, 0)]),
    "Initial Bump": (["posg"], "m/s²/s", False,
                     [(12, 10), (20, 8), (30, 6), (45, 3), (70, 0)]),
    "Bump": (["ax_pp", "shock"], "m/s²", False,
             [(0.3, 10), (0.6, 8), (1.0, 6), (1.8, 3), (3.0, 0)]),
    "Ax gradients during ratio change": (["posg"], "m/s²/s", False,
                                         [(10, 10), (20, 8), (30, 6), (45, 4), (70, 0)]),
    "Ax gradients after ratio change": (["negg"], "m/s²/s", False,
                                        [(8, 10), (15, 8), (25, 6), (40, 3), (60, 0)]),
    "Ax gradients before ratio change": (["negg"], "m/s²/s", False,
                                        [(8, 10), (15, 8), (25, 6), (40, 3), (60, 0)]),
    "Surge": (["negg"], "m/s²/s", False,
              [(8, 10), (15, 8), (25, 6), (40, 3), (60, 0)]),
    "Transition surge": (["negg"], "m/s²/s", False,
                         [(8, 10), (15, 8), (25, 6), (40, 3), (60, 0)]),
    "Acceleration disturbances": (["disturb_pp", "ax_pp", "idle_shake"], "m/s²", False,
                                [(0.2, 10), (0.5, 8), (0.9, 6), (1.4, 4), (2.5, 0)]),
    "Acceleration disturbances HF": (["disturb_pp"], "m/s²", False,
                                   [(0.15, 10), (0.4, 8), (0.7, 6), (1.2, 3), (2.0, 0)]),
    "Acceleration disturbances LF": (["disturb_pp"], "m/s²", False,
                                     [(0.2, 10), (0.5, 8), (0.9, 6), (1.4, 4), (2.5, 0)]),
    "Steadiness": (["linearity_pct"], "%", True,
                   [(98, 10), (92, 8), (85, 6), (75, 4), (60, 0)]),
    "Engagement steadiness": (["linearity_pct", "idle_shake"], "score", True,
                            [(95, 10), (88, 8), (80, 6), (70, 4), (55, 0)]),
    "Jerks": (["jerk_peak", "jerk_rms", "engage_jerk", "neg_jerk"], "m/s²/s", False,
              [(5, 10), (8, 8), (12, 6), (18, 4), (30, 0)]),
    "Engagement shock": (["jerk_peak", "engage_jerk"], "m/s²/s", False,
                         [(5, 10), (8, 8), (12, 6), (18, 4), (30, 0)]),
    "Brake release bump": (["jerk_peak", "ax_pp"], "m/s²/s", False,
                           [(5, 10), (8, 8), (12, 6), (18, 4), (30, 0)]),
    "Expected acceleration": (["ax_mean", "ax_peak"], "m/s²", True,
                              [(1.5, 6), (2.5, 8), (3.5, 10), (5.0, 10)]),
    "Reference acceleration": (["ax_peak"], "m/s²", True,
                               [(1.5, 6), (2.5, 8), (3.5, 10), (5.0, 10)]),
    "Acceleration peak": (["ax_peak"], "m/s²", True,
                          [(1.5, 6), (2.5, 8), (3.5, 10), (5.0, 10)]),
    "Acceleration performance": (["ax_peak", "t_to_10kph_ms"], "score", True,
                               [(2500, 10), (3500, 8), (5000, 6), (7000, 3)]),
    "Acceleration Performance": (["ax_peak", "t_to_10kph_ms"], "score", True,
                               [(2500, 10), (3500, 8), (5000, 6), (7000, 3)]),
    "Agility": (["posg", "resp_ms"], "score", True,
                [(200, 10), (350, 8), (500, 6), (700, 3)]),
    "Engine speed at engagement": (["rpm_start"], "rpm", True,
                                  [(1200, 6), (1800, 8), (2500, 10)]),
    "Start duration": (["start_ms", "restart_ms"], "ms", False,
                       [(400, 10), (600, 8), (900, 6), (1200, 4), (1800, 0)]),
    "Speed pickup duration": (["t_to_10kph_ms"], "ms", False,
                              [(2000, 10), (3000, 8), (4500, 6), (6000, 3), (9000, 0)]),
    "Idle stabilization duration": (["idle_shake"], "m/s²", False,
                                    [(0.03, 10), (0.06, 8), (0.10, 6), (0.15, 3), (0.25, 0)]),
    "Deceleration characteristic": (["decel_mean"], "m/s²", True,
                                   [(-3.5, 10), (-2.5, 8), (-1.5, 6), (-0.8, 3)]),
    "Decel. characteristic": (["decel_mean"], "m/s²", True,
                              [(-3.5, 10), (-2.5, 8), (-1.5, 6), (-0.8, 3)]),
    "Stumble": (["neg_jerk"], "m/s²/s", False,
                [(5, 10), (10, 8), (15, 6), (22, 3), (35, 0)]),
    "Brake release delay": (["launch_ms", "resp_ms"], "ms", False,
                            [(150, 10), (300, 8), (500, 6), (800, 3)]),
    "Brake release surge": (["negg", "posg"], "m/s²/s", False,
                            [(8, 10), (15, 8), (25, 6), (40, 3)]),
    "Response": (["resp_ms", "tot_ms"], "ms", False,
                 [(150, 10), (300, 8), (500, 6), (800, 3)]),
    "Torque build-up": (["posg"], "m/s²/s", True,
                        [(8, 6), (15, 8), (25, 10), (40, 8)]),
    "Torque response": (["resp_ms", "tot_ms"], "ms", False,
                        [(150, 10), (300, 8), (500, 6), (800, 3)]),
    "Torque smoothness": (["linearity_pct", "jerk_rms"], "score", True,
                          [(95, 10), (88, 8), (80, 6), (70, 4)]),
    "Transition shock": (["shock", "jerk_peak"], "m/s²", False,
                         [(0.3, 10), (0.6, 8), (1.0, 6), (1.5, 3)]),
    "Engine speed change": (["rpm_peak"], "rpm", False,
                            [(300, 10), (500, 8), (800, 6), (1200, 3)]),
    "Engine speed fluctuations": (["idle_shake"], "m/s²", False,
                                  [(0.03, 10), (0.06, 8), (0.10, 6), (0.15, 3)]),
    "Engine speed undershoot": (["rpm_start"], "rpm", False,
                                [(200, 10), (400, 8), (600, 6), (900, 3)]),
    "Engine speed stumble": (["rpm_peak"], "rpm", False,
                             [(300, 10), (500, 8), (800, 6), (1200, 3)]),
    "Longitudinal acceleration": (["ax_peak", "ax_mean"], "m/s²", True,
                                [(1.5, 6), (2.5, 8), (3.5, 10)]),
    "Acceleration increase": (["posg"], "m/s²/s", True,
                              [(8, 6), (15, 8), (25, 10)]),
    "Clutch grabbing": (["engage_jerk", "jerk_peak"], "m/s²/s", False,
                        [(5, 10), (8, 8), (12, 6), (18, 3)]),
    "Clutch surge": (["negg", "fs"], "m/s²/s", False,
                     [(8, 10), (15, 8), (25, 6), (40, 3)]),
    "Engagement point": (["launch_ms", "resp_ms"], "ms", False,
                         [(200, 10), (350, 8), (500, 6), (800, 3)]),
    "Starter response delay": (["start_ms"], "ms", False,
                               [(400, 10), (600, 8), (900, 6), (1200, 3)]),
    "Traction reduction": (["negg"], "m/s²/s", False,
                           [(8, 10), (15, 8), (25, 6), (40, 3)]),
    "Speed increase": (["ax_peak"], "m/s²", True,
                       [(1.0, 6), (2.0, 8), (3.0, 10)]),
    "Speed decrease": (["decel_peak"], "m/s²", True,
                       [(-3.5, 10), (-2.5, 8), (-1.5, 6)]),
    "Speed decrease delay": (["dec_ms", "tot_ms"], "ms", False,
                             [(150, 10), (300, 8), (500, 6), (800, 3)]),
    "Engine speed drift": (["idle_shake"], "m/s²", False,
                           [(0.03, 10), (0.06, 8), (0.10, 6), (0.15, 3)]),
    "Shift characteristic": (["exec_ms", "shock"], "score", True,
                             [(400, 8), (300, 10), (600, 6)]),
    "Speed increase delay": (["tot_ms", "resp_ms"], "ms", False,
                             [(150, 10), (300, 8), (500, 6), (800, 3)]),
    "Acceleration overshoot": (["ax_peak"], "m/s²", False,
                               [(3.0, 10), (4.5, 8), (6.0, 5), (8.0, 2)]),
    "Acceleration decrease": (["decel_peak"], "m/s²", True,
                             [(-3.5, 10), (-2.5, 8), (-1.5, 6)]),
    "Flare": (["rpm_peak"], "rpm", False,
              [(300, 10), (500, 8), (800, 6), (1200, 3)]),
    "Engine speed step": (["rpm_peak"], "rpm", False,
                          [(300, 10), (500, 8), (800, 6)]),
    "Duration 0-100 kph": (["t_to_10kph_ms"], "ms", False,
                           [(5000, 10), (7000, 8), (9000, 6), (12000, 3)]),
    "Engine speed drop": (["rpm_drop", "rpm_start"], "rpm", False,
                          [(0, 10), (200, 7), (400, 4), (600, 0)]),
    "Engine speed overshoot": (["rpm_peak"], "rpm", False,
                               [(300, 10), (500, 8), (800, 6), (1200, 3)]),
    "Ax increase": (["posg"], "m/s²/s", True,
                    [(8, 6), (15, 8), (25, 10), (40, 8)]),
    "Stall sensitivity": (["rpm_min", "rpm_drop"], "rpm", True,
                          [(800, 10), (600, 7), (400, 4), (200, 0)]),
    "Engine stall": (["rpm_min"], "rpm", True,
                     [(800, 10), (600, 7), (400, 4), (200, 0)]),
    "Required pedal position": (["pedal_at_launch", "pedal_mean"], "%", False,
                                [(20, 10), (40, 7), (60, 4), (80, 0)]),
}

# Aliases for case / punctuation variants in ODRIV exports
ALIASES = {
    "acceleration performance": "Acceleration performance",
}


def _interp_rating(value: float, anchors: list, higher_is_better: bool) -> float:
    if value is None:
        return None
    v = float(value)
    if not higher_is_better:
        v = abs(v)
    pts = sorted(anchors, key=lambda p: p[0])
    if higher_is_better:
        pts = sorted(anchors, key=lambda p: p[0])
        if v <= pts[0][0]:
            return float(pts[0][1])
        if v >= pts[-1][0]:
            return float(pts[-1][1])
        for (x0, r0), (x1, r1) in zip(pts, pts[1:]):
            if x0 <= v <= x1:
                f = (v - x0) / (x1 - x0) if x1 != x0 else 0
                return round(r0 + f * (r1 - r0), 2)
    else:
        if v <= pts[0][0]:
            return float(pts[0][1])
        if v >= pts[-1][0]:
            return float(pts[-1][1])
        for (x0, r0), (x1, r1) in zip(pts, pts[1:]):
            if x0 <= v <= x1:
                f = (v - x0) / (x1 - x0) if x1 != x0 else 0
                return round(r0 + f * (r1 - r0), 2)
    return None


def _physical(metrics: dict, keys: list):
    for k in keys:
        val = metrics.get(k)
        if val is not None:
            return val, k
    return None, None


def measure_criterion(name: str, metrics: dict):
    """Return (physical_value, unit, metric_key) or (None, None, None)."""
    key = ALIASES.get(name.lower(), name)
    spec = ANCHORS.get(key)
    if not spec:
        return None, None, None
    keys, unit, _, _ = spec
    val, used = _physical(metrics, keys)
    if val is None:
        return None, unit, None
    return val, unit, used


def rate_criterion(name: str, metrics: dict):
    """Return (physical, unit, rating_0_10) or Nones."""
    key = ALIASES.get(name.lower(), name)
    spec = ANCHORS.get(key)
    phys, unit, _ = measure_criterion(name, metrics)
    if phys is None or spec is None:
        return phys, unit, None
    _, _, higher, anchors = spec
    rating = _interp_rating(phys, anchors, higher)
    return phys, unit, rating


def verdict_for_rating(rating: float | None, target: float, warn_limit: float) -> str:
    """AVL-style: rating must meet target (t); warn limit (wl) is the lower acceptable bound."""
    if rating is None:
        return "na"
    if rating >= target:
        return "ok"
    if rating >= warn_limit:
        return "warn"
    return "bad"


def evaluate_mode(mode_name: str, metrics: dict, criteria_db: dict | None = None) -> list[dict]:
    """Evaluate all criteria for an operation mode against measured metrics."""
    db = criteria_db if criteria_db is not None else edo_loader.load()
    rows = db.get(mode_name, [])
    out = []
    for c in rows:
        name = c["criteria"]
        phys, unit, rating = rate_criterion(name, metrics)
        t, wl = float(c.get("t", 8)), float(c.get("wl", 7))
        sev = verdict_for_rating(rating, t, wl)
        out.append({
            "criteria": name,
            "t": t,
            "wl": wl,
            "driv": c.get("driv"),
            "physical": (round(phys, 3) if phys is not None and isinstance(phys, float) else phys),
            "unit": unit,
            "rating": rating,
            "measured": (
                f"{rating:.1f}" if rating is not None
                else (f"{phys} {unit}" if phys is not None else None)
            ),
            "sev": sev,
        })
    out.sort(key=lambda r: (r["rating"] is None, r.get("driv") or 9))
    return out


def summarize_verdict(rows: list[dict]) -> str:
    worst = "ok"
    for r in rows:
        if r["sev"] == "bad":
            return "bad"
        if r["sev"] == "warn":
            worst = "warn"
    measured = [r for r in rows if r["sev"] != "na"]
    return worst if measured else "ok"


def issues_from_criteria(rows: list[dict]) -> list[dict]:
    """Turn failed ODRIV criteria into issue dicts for the dashboard."""
    issues = []
    for r in rows:
        if r["sev"] not in ("warn", "bad"):
            continue
        if r["rating"] is None:
            continue
        phys = f" ({r['physical']} {r['unit']})" if r.get("physical") is not None else ""
        issues.append({
            "title": r["criteria"],
            "severity": r["sev"],
            "value": f"{r['rating']:.1f}/10",
            "detail": (
                f"ODRIV rating {r['rating']:.1f} vs target {r['t']:.1f} "
                f"(warn {r['wl']:.1f}){phys}."
            ),
        })
    return issues


def actions_from_criteria(rows: list[dict]) -> list[dict]:
    """Map highest-priority failed criteria to calibration hints."""
    hints = {
        "Response delay": ("Reduce response / hesitation", "Shorten torque-onset delay and gear-decision time."),
        "Shift duration": ("Reduce shift execution time", "Tune clutch fill, sync, and torque handover."),
        "Shift delay": ("Reduce shift decision time", "Review shift-map trigger thresholds and pre-selection."),
        "Shock": ("Soften torque handover", "Shape clutch re-apply and engine torque for continuous wheel torque."),
        "Ax gradients during ratio change": ("Rate-limit engagement snatch", "Soften torque apply gradient at ratio change."),
        "Surge": ("Anti-shunt / shuffle damping", "Tune lash management and driveline damping at measured frequency."),
        "Acceleration disturbances": ("Smooth steady-state torque", "Check tip-in filtering, torque smoothing, lash handling."),
        "Steadiness": ("Linearise pedal-to-accel", "Smooth driver-demand to wheel-torque mapping."),
        "Jerks": ("Reduce jerk peaks", "Rate-limit torque steps through engagement and lash crossing."),
        "Engagement shock": ("Smooth launch / engagement", "Soften initial torque ramp and clutch fill."),
        "Stumble": ("Soften tip-out / overrun", "Rate-limit negative torque on lift-off."),
    }
    actions = []
    failed = [r for r in rows if r["sev"] in ("warn", "bad") and r["rating"] is not None]
    failed.sort(key=lambda r: (r.get("driv") or 9, r["sev"] == "warn"))
    seen = set()
    pri = 1
    for r in failed:
        if r["criteria"] in seen:
            continue
        seen.add(r["criteria"])
        title, detail = hints.get(r["criteria"], (
            f"Improve {r['criteria'].lower()}",
            f"Criterion rated {r['rating']:.1f}/10 vs target {r['t']:.1f}.",
        ))
        actions.append({"priority": pri, "title": title, "detail": detail})
        pri += 1
        if pri > 4:
            break
    return actions
