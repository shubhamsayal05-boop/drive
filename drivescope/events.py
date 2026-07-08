"""Multi-mode drivability event detection (AVL-DRIVE-style operation modes).

Detects, from measured signals, the maneuver types calibrators care about:
  - drive_away            launch from standstill (engine running)
  - drive_away_ess        launch from standstill after engine stop-start
  - accel_constant_load   sustained acceleration at ~constant pedal
  - accel_load_increase   acceleration with rising pedal (load build)
  - kickdown_downshift    tip-in + downshift
  - poweron_upshift       upshift under load
  - tip_out_overrun       lift-off / coast-down

Detection prefers recorded state flags (standstill, stop-start) when present,
and degrades gracefully when channels are missing.
"""
import numpy as np

# thresholds (tune in one place)
V_STILL = 1.5        # kph below which the vehicle is "stopped"
V_MOVE = 2.5         # kph above which it is "moving"
PED_ON = 15.0        # % pedal considered "applied"
PED_TIPIN = 50.0     # % rising edge for a tip-in
ENG_OFF = 100.0      # rpm below which the engine is "off" (ESS)
ACC_MIN_DUR = 1.2    # s minimum sustained acceleration segment
ACC_MAX_DUR = 6.0    # s cap on a segment window
PED_FLAT_STD = 6.0   # % pedal std below which load is "constant"
PRE, POST = 1.0, 3.0


def _grid_all(rec, dt=0.02):
    t0, t1 = rec.duration()
    grid = np.arange(t0, t1, dt)
    sig = {"t": grid}
    for c in ["pedal", "vehicle_speed", "engine_speed", "gear_act", "ax_filt",
              "standstill", "stopstart", "brake"]:
        r = rec.resample(c, grid)
        if r is not None:
            sig[c] = r
    return sig


def _segments(mask, grid, min_dur):
    """Return [(t_start, t_end)] for contiguous True runs >= min_dur."""
    out = []
    if mask is None:
        return out
    idx = np.where(mask)[0]
    if not len(idx):
        return out
    splits = np.where(np.diff(idx) > 1)[0]
    groups = np.split(idx, splits + 1)
    for g in groups:
        if grid[g[-1]] - grid[g[0]] >= min_dur:
            out.append((float(grid[g[0]]), float(grid[g[-1]])))
    return out


def detect(rec, max_events=24, cfg=None):
    TH = (cfg or {}).get("thresholds", {}) if cfg else {}
    zero_speed = float(TH.get("zero_speed_kph", 1.5))
    kd_pedal = float(TH.get("kickdown_pedal_pct", 98.0))
    tip_rate = float(TH.get("tip_rate_pct_s", 200.0))
    decel_brk = float(TH.get("decel_brake_pct", 3.0))
    s = _grid_all(rec)
    g = s["t"]
    ped = s.get("pedal"); veh = s.get("vehicle_speed"); rpm = s.get("engine_speed")
    gear = s.get("gear_act"); ax = s.get("ax_filt")
    still = s.get("standstill"); ss = s.get("stopstart")
    events = []
    used = []

    def overlaps(t):
        return any(abs(t - u) < 0.6 for u in used)

    def add(ev):
        if overlaps(ev["t_trigger"]):
            return
        used.append(ev["t_trigger"]); events.append(ev)

    moving = veh > V_MOVE if veh is not None else None
    stopped = (still > 0.5) if still is not None else (veh <= V_STILL if veh is not None else None)

    # ---------- DRIVE-AWAY (and ESS) ----------
    # Offset-robust: "stopped" is relative to the recording's resting speed level,
    # so a non-zero speed bias at standstill (common) does not hide the launch.
    if veh is not None and ped is not None:
        base = float(np.nanpercentile(veh, 5))          # resting speed level
        still_lvl = base + max(1.5, zero_speed)
        move_lvl = max(base + 4.0, zero_speed + 3.0)
        still_mask = veh < still_lvl
        for (sa, sb) in _segments(still_mask, g, 0.3):   # sustained stop >= 0.3 s
            wlaunch = (g > sb) & (g <= sb + 3.0) & (veh > move_lvl)
            idx = np.where(wlaunch)[0]
            if not len(idx):
                continue
            tl = float(g[idx[0]])
            wp = (g >= sb - 0.3) & (g <= tl + 0.3)
            if ped[wp].max() < 3:                         # low-% launches exist (e.g. ESS 5%)
                continue
            ess = False
            pre = (g >= sa) & (g <= sb)
            if rpm is not None and pre.any() and np.nanmin(rpm[pre]) < ENG_OFF:
                ess = True
            if ss is not None and pre.any() and np.nanmax(ss[pre]) > 0.5:
                ess = True
            etype = "drive_away_ess" if ess else "drive_away"
            label = "Drive-away (ESS restart)" if ess else "Drive-away (launch)"
            add({"type": etype, "label": label, "t_trigger": round(tl, 2), "t_shift": round(tl, 2),
                 "t0": tl - PRE, "t1": tl + POST, "gear_from": None, "gear_to": None})

    # ---------- SHIFTS (tip-in downshift / power-on upshift) ----------
    if ped is not None and gear is not None:
        gr = np.round(gear)
        chg = np.where(np.diff(gr) != 0)[0]
        tipins = g[np.where((ped[:-1] < PED_TIPIN) & (ped[1:] >= PED_TIPIN))[0]]
        for i in chg:
            tchg = float(g[i + 1]); g0, g1 = int(gr[i]), int(gr[i + 1])
            if g1 == g0:
                continue
            ped_here = float(ped[i + 1])
            near_tip = np.any(np.abs(tipins - tchg) < 1.5)
            if g1 < g0 and near_tip:
                kd = "kickdown_downshift"
                lbl = (f"Kick-down ({g0}→{g1})" if ped_here >= kd_pedal else f"Tip-in Downshift ({g0}→{g1})")
                add({"type": kd, "label": lbl,
                     "t_trigger": float(tipins[np.argmin(np.abs(tipins - tchg))]), "t_shift": tchg,
                     "t0": tchg - PRE - 0.5, "t1": tchg + POST, "gear_from": g0, "gear_to": g1})
            elif g1 > g0 and ped_here > 20:
                add({"type": "poweron_upshift", "label": f"Power-on Upshift ({g0}→{g1})",
                     "t_trigger": tchg - 0.3, "t_shift": tchg,
                     "t0": tchg - PRE, "t1": tchg + POST, "gear_from": g0, "gear_to": g1})

    # ---------- ACCELERATION SEGMENTS (constant load / load increase) ----------
    if veh is not None and ped is not None and moving is not None:
        dv = np.gradient(veh, g)
        accel_mask = moving & (ped > 25) & (dv > 0.5)
        for (ta, tb) in _segments(accel_mask, g, ACC_MIN_DUR):
            tb = min(tb, ta + ACC_MAX_DUR)
            w = (g >= ta) & (g <= tb)
            pstd = float(np.std(ped[w]))
            pslope = float(np.polyfit(g[w], ped[w], 1)[0])  # %/s
            if pstd < PED_FLAT_STD and abs(pslope) < 8:
                etype, label = "accel_constant_load", "Acceleration – Constant Load"
            elif pslope >= 8:
                etype, label = "accel_load_increase", "Acceleration – Load Increase"
            else:
                continue
            add({"type": etype, "label": label, "t_trigger": ta, "t_shift": ta,
                 "t0": ta - 0.3, "t1": tb + 0.3, "gear_from": None, "gear_to": None})

    # ---------- GARAGE SHIFT / LEVER CHANGE ----------
    sel = s.get("selector")
    lever_sig, lever_name = (sel, "selector") if sel is not None else (gear, "gear_act")
    if lever_sig is not None and veh is not None:
        sr = np.round(lever_sig)
        chg = np.where(np.diff(sr) != 0)[0]
        for i in chg:
            tc = float(g[i + 1])
            j = min(i + 1, len(veh) - 1)
            idle_pedal = (ped is None) or (ped[j] < 5)
            if veh[j] < 2.0 and idle_pedal:                # lever moved at standstill, off pedal
                add({"type": "lever_change", "label": "Garage shift / Lever change",
                     "t_trigger": tc, "t_shift": tc, "t0": tc - 1.0, "t1": tc + 2.0,
                     "gear_from": None, "gear_to": None})

    # ---------- TIP-IN AT CONSTANT SPEED ----------
    if ped is not None and veh is not None:
        dt_g = float(g[1] - g[0]) if len(g) > 1 else 0.02
        prate = np.gradient(ped, dt_g)                  # %/s
        rises = np.where((ped[:-1] < 22) & (ped[1:] >= 28))[0]
        for i in rises:
            tc = float(g[i + 1])
            if veh[i + 1] > 5 and prate[i] >= tip_rate * 0.5 and not any(abs(tc - u) < 1.2 for u in used):
                add({"type": "tip_in_cstspd", "label": "Tip-in at constant speed",
                     "t_trigger": tc, "t_shift": tc, "t0": tc - 1.0, "t1": tc + 2.5,
                     "gear_from": None, "gear_to": None})

    # ---------- TIP-OUT AT CONSTANT SPEED / OVERRUN ----------
    if ped is not None and veh is not None:
        # windowed: pedal sustained >12 then falls to <=6 within ~1.5 s (handles ramp tip-out)
        hi = ped > 12
        for (ha, hb) in _segments(hi, g, 0.3):
            wa = (g > hb) & (g <= hb + 1.5)
            idx = np.where(wa & (ped <= 6))[0]
            if len(idx):
                tc = float(g[idx[0]])
                if veh[idx[0]] > 5:
                    add({"type": "tip_out_cstspd", "label": "Tip-out at constant speed",
                         "t_trigger": float(hb), "t_shift": float(hb), "t0": hb - 0.6, "t1": tc + 2.0,
                         "gear_from": None, "gear_to": None})

    # ---------- DECELERATION (coast / braking) ----------
    brk = s.get("brake")
    if ax is not None and veh is not None:
        decel_mask = (ax < -0.6) & (veh > 5) & ((ped < 12) if ped is not None else True)
        for (ta, tb) in _segments(decel_mask, g, 1.0):
            tb = min(tb, ta + ACC_MAX_DUR)
            w = (g >= ta) & (g <= tb)
            braking = bool(brk is not None and np.nanmax(brk[w]) > 0.1)
            etype = "decel_brake" if braking else "decel_coast"
            label = "Deceleration (braking)" if braking else "Deceleration (coast / no brake)"
            add({"type": etype, "label": label, "t_trigger": ta, "t_shift": ta,
                 "t0": ta - 0.3, "t1": tb + 0.3, "gear_from": None, "gear_to": None})

    # ---------- ENGINE START / STOP / IDLE (stationary) ----------
    if rpm is not None:
        run = rpm > 400
        starts = np.where((~run[:-1]) & (run[1:]))[0]
        stops = np.where((run[:-1]) & (~run[1:]))[0]
        stationary = (veh < 2.0) if veh is not None else np.ones_like(g, bool)
        for i in starts:
            if stationary[min(i + 1, len(stationary) - 1)]:
                tc = float(g[i + 1])
                add({"type": "engine_start", "label": "Engine start (stationary)",
                     "t_trigger": tc, "t_shift": tc, "t0": tc - 1.0, "t1": tc + 2.0,
                     "gear_from": None, "gear_to": None})
        for i in stops:
            if stationary[min(i + 1, len(stationary) - 1)]:
                tc = float(g[i + 1])
                add({"type": "engine_stop", "label": "Engine stop (stationary)",
                     "t_trigger": tc, "t_shift": tc, "t0": tc - 1.0, "t1": tc + 2.0,
                     "gear_from": None, "gear_to": None})
        # if nothing else found and the car idles stationary the whole time -> Idle event
        if not events and veh is not None and np.nanmax(veh) < 2.0 and np.nanmax(rpm) > 400:
            mid = float(g[len(g) // 2])
            add({"type": "idle", "label": "Idle (vehicle stationary)",
                 "t_trigger": float(g[0]) + 1, "t_shift": float(g[0]) + 1,
                 "t0": float(g[0]), "t1": min(float(g[-1]), float(g[0]) + 6),
                 "gear_from": None, "gear_to": None})

    # ---------- TIP-OUT / OVERRUN (legacy strong tip-out) ----------
    if ped is not None and moving is not None:
        tipouts = g[np.where((ped[:-1] > 25) & (ped[1:] <= 5))[0]]
        for to in tipouts:
            i = int(np.argmin(np.abs(g - to)))
            if moving[i]:
                add({"type": "tip_out_overrun", "label": "Tip-out / Overrun", "t_trigger": float(to),
                     "t_shift": float(to), "t0": float(to) - 0.6, "t1": float(to) + 2.5,
                     "gear_from": None, "gear_to": None})

    events.sort(key=lambda e: e["t_trigger"])
    return events[:max_events]


def maneuver_hint(path):
    """Infer the tested maneuver family from the recording / collector name, the way
    ODRIV keys off the event-collector (e.g. AT_Vxx_DriveAway_ESS.ect). Returns a set
    of allowed event types, or None when the name gives no hint."""
    import os
    n = os.path.basename(str(path)).lower()
    if "ess" in n or "dass" in n:
        return {"drive_away_ess", "drive_away"}
    if n.startswith("gs") or "garage" in n or "_rlmc" in n:
        return {"lever_change"}
    if "rrl" in n or "rolling" in n:
        return {"drive_away", "accel_constant_load", "poweron_upshift"}
    if "ti_cstspd" in n or "ticstspd" in n or n.startswith("ti_"):
        return {"tip_in_cstspd", "poweron_upshift", "accel_constant_load"}
    if "to_cstspd" in n or "tocstspd" in n or n.startswith("to_"):
        return {"tip_out_cstspd", "decel_coast", "decel_brake"}
    if "decel" in n:
        return {"decel_coast", "decel_brake"}
    if "stationary" in n or "startstop" in n or "start_stop" in n or "idle" in n:
        return {"engine_start", "engine_stop", "idle"}
    if "rtito" in n:
        return {"kickdown_downshift", "tip_out_overrun", "tip_out_cstspd",
                "accel_constant_load", "poweron_upshift", "tip_in_cstspd", "drive_away"}
    if "driveaway" in n or n.startswith("da_") or "drive_away" in n:
        return {"drive_away", "drive_away_ess"}
    if "kickdown" in n or n.startswith("kd"):
        return {"kickdown_downshift"}
    return None


def summarize(rec):
    """Coarse recording summary so the UI can explain why detection did/didn't fire."""
    s = _grid_all(rec)
    g = s["t"]
    def rng(k, dec=1):
        v = s.get(k)
        if v is None:
            return None
        return {"min": round(float(np.nanmin(v)), dec), "max": round(float(np.nanmax(v)), dec)}
    out = {"signals": {}}
    for k in ["vehicle_speed", "pedal", "engine_speed", "gear_act", "ax_filt"]:
        r = rng(k, 2 if k == "ax_filt" else 1)
        if r:
            out["signals"][k] = r
    veh = s.get("vehicle_speed"); ped = s.get("pedal"); gear = s.get("gear_act")
    if veh is not None:
        base = float(np.nanpercentile(veh, 5))
        out["standstill_segments"] = len(_segments(veh < base + 1.5, g, 0.3))
    if ped is not None:
        out["tipins"] = int(np.sum((ped[:-1] < PED_TIPIN) & (ped[1:] >= PED_TIPIN)))
        out["pedal_applied"] = bool(np.nanmax(ped) > PED_ON)
    if gear is not None:
        gr = np.round(gear)
        out["gear_changes"] = int(np.sum(np.diff(gr) != 0))
        out["gears_seen"] = sorted(set(int(x) for x in np.unique(gr) if np.isfinite(x)))
    return out
