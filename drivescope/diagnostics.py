"""Per-maneuver issue detection, KPI cards, and calibration suggestions.

Uses Operation Modes Criteria (.edo / sdv_criteria.json) for ODRIV-aligned
0–10 ratings where measurable; retains physical KPI cards for the dashboard.
"""
from . import criteria as crit_mod
from . import avl_map

TH = {
    "resp_warn": 350, "resp_bad": 500, "exec_warn": 400, "exec_bad": 600,
    "posg_warn": 20, "posg_bad": 35, "negg_warn": 15, "negg_bad": 28,
    "shock_warn": 0.6, "shock_bad": 1.0,
    "launch_warn": 300, "launch_bad": 500, "restart_warn": 450, "restart_bad": 700,
    "disturb_warn": 0.5, "disturb_bad": 1.0, "jerk_warn": 8, "jerk_bad": 15,
    "lin_warn": 90, "lin_bad": 80,
}


def _sev(v, warn, bad, invert=False):
    if v is None:
        return "na"
    a = abs(v)
    if invert:  # higher is better (e.g. linearity %)
        return "bad" if a < bad else "warn" if a < warn else "ok"
    return "bad" if a >= bad else "warn" if a >= warn else "ok"


def diagnose(ev, m):
    t = ev["type"]
    issues, actions, kpis = [], [], []

    def kpi(k, v, sub, sev): kpis.append({"k": k, "v": v, "sub": sub, "sev": sev})
    def issue(title, sev, value, detail): issues.append({"title": title, "severity": sev, "value": value, "detail": detail})
    def act(p, title, detail): actions.append({"priority": p, "title": title, "detail": detail})

    if t in ("kickdown_downshift", "poweron_upshift"):
        if t == "kickdown_downshift":
            tot, exe, dec = m.get("tot_ms"), m.get("exec_ms"), m.get("dec_ms")
            kpi("Response delay", f"{tot if tot is not None else '—'}<small> ms</small>", "tip-in → accel", _sev(tot, TH["resp_warn"], TH["resp_bad"]))
            kpi("Shift execution", f"{exe if exe is not None else '—'}<small> ms</small>", f"decide {dec} ms · execute {exe} ms", _sev(exe, TH["exec_warn"], TH["exec_bad"]))
            kpi("Snatch", f"+{m.get('posg','—')}", "ax grad m/s²/s" + (f" (raw +{m['posg_r']})" if m.get("posg_r") is not None else ""), _sev(m.get("posg"), TH["posg_warn"], TH["posg_bad"]))
            kpi("Surge", f"{m.get('fs','—')}<small> Hz</small>", f"{m.get('negg','—')} m/s²/s ringdown", _sev(m.get("negg"), TH["negg_warn"], TH["negg_bad"]))
            if tot is not None:
                issue("Response delay (hesitation)", _sev(tot, TH["resp_warn"], TH["resp_bad"]), f"{tot} ms",
                      f"Tip-in to acceleration onset is {tot} ms — the driver demands full power but the vehicle does not respond for ~{tot/1000:.1f} s.")
            if exe is not None:
                s = _sev(exe, TH["exec_warn"], TH["exec_bad"])
                issue("Shift execution time", s, f"{exe} ms",
                      (f"Decision is fast ({dec} ms); " if dec is not None else "") + f"the shift takes {exe} ms to physically execute (clutch fill + spin-up + sync) — the bottleneck.")
                if s != "ok":
                    act(1, "Reduce shift execution time", "Target clutch fill time/pressure, off-going release coordination, engine spin-up assist. Shift-map decision is not the issue.")
            if m.get("posg") is not None and _sev(m["posg"], TH["posg_warn"], TH["posg_bad"]) != "ok":
                issue("Engagement snatch", _sev(m["posg"], TH["posg_warn"], TH["posg_bad"]), f"+{m['posg']} m/s²/s", "Torque lands fast at engagement — a jolt through the seat.")
                act(2, "Rate-limit torque onset", "Shape the apply (clutch-slip target ramp + engine torque coordination) to cut the snatch without re-adding delay.")
            if m.get("negg") is not None and abs(m["negg"]) >= TH["negg_warn"]:
                fs = f" at {m['fs']} Hz" if m.get("fs") else ""
                issue("Driveline surge", _sev(m["negg"], TH["negg_warn"], TH["negg_bad"]), f"{m['negg']} m/s²/s", f"Lash take-up + ringdown{fs} after the snatch.")
                act(3, f"Anti-shunt damping{fs}", "Lash management + active driveline damping at the measured shuffle frequency.")
        else:  # upshift
            kpi("Upshift shock", f"{m.get('shock','—')}", "m/s² handover step", _sev(m.get("shock"), TH["shock_warn"], TH["shock_bad"]))
            kpi("Shuffle", f"{m.get('fs','—')}<small> Hz</small>", "post-shift ringdown", "warn" if m.get("fs") else "na")
            kpi("ax neg grad", f"{m.get('negg','—')}", "m/s²/s", _sev(m.get("negg"), TH["negg_warn"], TH["negg_bad"]))
            kpi("Peak ax", f"{m.get('ax_peak','—')}", "m/s²", "ok")
            if m.get("shock") is not None and _sev(m["shock"], TH["shock_warn"], TH["shock_bad"]) != "ok":
                issue("Upshift shock", _sev(m["shock"], TH["shock_warn"], TH["shock_bad"]), f"{m['shock']} m/s²", "Torque-handover step at re-engagement — a discrete bump.")
                act(1, "Soften torque handover", "Shape inertia-phase exit / clutch re-apply gradient; coordinate engine torque so wheel torque stays continuous.")
            if m.get("negg") is not None and abs(m["negg"]) >= TH["negg_warn"]:
                fs = f" at {m['fs']} Hz" if m.get("fs") else ""
                issue("Post-shift shuffle", _sev(m["negg"], TH["negg_warn"], TH["negg_bad"]), f"{m['negg']} m/s²/s", f"Driveline rings down{fs}.")
                act(2, f"Active driveline damping{fs}", "Tune anti-shuffle torque modulation at the driveline natural frequency.")

    elif t in ("drive_away", "drive_away_ess"):
        lm = m.get("launch_ms")
        kpi("Launch delay", f"{lm if lm is not None else '—'}<small> ms</small>", "pedal → accel", _sev(lm, TH["launch_warn"], TH["launch_bad"]))
        if t == "drive_away_ess":
            rm = m.get("restart_ms")
            kpi("ESS restart", f"{rm if rm is not None else '—'}<small> ms</small>", "engine off → running", _sev(rm, TH["restart_warn"], TH["restart_bad"]))
        else:
            kpi("Time to 10 kph", f"{m.get('t_to_10kph_ms','—')}<small> ms</small>", "from release", "ok")
        kpi("Peak ax", f"{m.get('ax_peak','—')}", "m/s² launch", "ok")
        kpi("Launch jerk", f"{m.get('jerk_peak','—')}", "m/s²/s" + (f" · {m['fs']} Hz" if m.get("fs") else ""), _sev(m.get("jerk_peak"), TH["jerk_warn"], TH["jerk_bad"]))
        if lm is not None and _sev(lm, TH["launch_warn"], TH["launch_bad"]) != "ok":
            issue("Launch hesitation", _sev(lm, TH["launch_warn"], TH["launch_bad"]), f"{lm} ms", f"Delay from pedal apply to acceleration is {lm} ms — sluggish drive-away feel.")
            act(1, "Improve launch response", "Tune launch torque ramp / clutch (or e-motor torque) fill and creep-to-drive transition.")
        if t == "drive_away_ess" and m.get("restart_ms") is not None and _sev(m["restart_ms"], TH["restart_warn"], TH["restart_bad"]) != "ok":
            issue("ESS restart delay", _sev(m["restart_ms"], TH["restart_warn"], TH["restart_bad"]), f"{m['restart_ms']} ms", "Engine restart adds latency to the drive-away after a stop-start event.")
            act(1, "Speed up / mask ESS restart", "Optimise restart cranking + torque availability; consider pre-emptive restart on brake-release.")
        if m.get("jerk_peak") is not None and abs(m["jerk_peak"]) >= TH["jerk_warn"]:
            issue("Launch jerk / shudder", _sev(m["jerk_peak"], TH["jerk_warn"], TH["jerk_bad"]), f"{m['jerk_peak']} m/s²/s", "Abrupt take-up at launch.")
            act(2, "Smooth launch take-up", "Soften initial torque gradient and clutch engagement to remove the jerk.")

    elif t in ("accel_constant_load", "accel_load_increase"):
        kpi("Mean ax", f"{m.get('ax_mean','—')}", f"m/s² @ {m.get('pedal_mean','?')}% pedal", "ok")
        kpi("Smoothness", f"{m.get('linearity_pct','—')}<small> %</small>", "100 = perfectly linear", _sev(m.get("linearity_pct"), TH["lin_warn"], TH["lin_bad"], invert=True))
        kpi("Disturbance", f"{m.get('disturb_pp','—')}", "m/s² peak-peak", _sev(m.get("disturb_pp"), TH["disturb_warn"], TH["disturb_bad"]))
        kpi("Jerk RMS", f"{m.get('jerk_rms','—')}", "m/s²/s" + (f" · {m['fs']} Hz" if m.get("fs") else ""), _sev(m.get("jerk_rms"), TH["jerk_warn"], TH["jerk_bad"]))
        if m.get("disturb_pp") is not None and _sev(m["disturb_pp"], TH["disturb_warn"], TH["disturb_bad"]) != "ok":
            fs = f" ({m['fs']} Hz)" if m.get("fs") else ""
            issue("Acceleration disturbance", _sev(m["disturb_pp"], TH["disturb_warn"], TH["disturb_bad"]), f"{m['disturb_pp']} m/s²", f"Acceleration is not smooth{fs} — surge/oscillation on top of the steady pull.")
            act(1, f"Reduce steady-state surge{fs}", "Check tip-in/anti-shuffle filtering, torque smoothing, and lash handling during constant-load accel.")
        if m.get("linearity_pct") is not None and _sev(m["linearity_pct"], TH["lin_warn"], TH["lin_bad"], invert=True) != "ok":
            issue("Acceleration linearity", _sev(m["linearity_pct"], TH["lin_warn"], TH["lin_bad"], invert=True), f"{m['linearity_pct']} %", "Pull is uneven for a constant pedal — hurts the 'connected/linear' feel.")
            act(2, "Linearise pedal-to-accel map", "Smooth the driver-demand / torque-to-wheel mapping so constant pedal yields constant build-up.")

    elif t == "lever_change":
        kpi("Engagement jerk", f"{m.get('engage_jerk','—')}", "m/s²/s", _sev(m.get("engage_jerk"), TH["jerk_warn"], TH["jerk_bad"]))
        kpi("Shock (ax p-p)", f"{m.get('ax_pp','—')}", "m/s²", _sev(m.get("ax_pp"), TH["shock_warn"], TH["shock_bad"]))
        kpi("Shuffle", f"{m.get('fs','—')}<small> Hz</small>", "engagement ringdown", "warn" if m.get("fs") else "na")
        kpi("—", "—", "", "na")
        if m.get("engage_jerk") is not None and abs(m["engage_jerk"]) >= TH["jerk_warn"]:
            issue("Garage-shift clunk", _sev(m["engage_jerk"], TH["jerk_warn"], TH["jerk_bad"]), f"{m['engage_jerk']} m/s²/s", "Abrupt engagement when moving the selector (R/D) — driveline clunk/shock.")
            act(1, "Smooth garage-shift engagement", "Soften clutch/converter engagement torque on lever change; manage lash take-up at engagement.")

    elif t == "tip_out_overrun":
        kpi("Decel ax", f"{m.get('ax_min','—')}", "m/s² lift-off", "ok")
        kpi("Neg jerk", f"{m.get('neg_jerk','—')}", "m/s²/s", _sev(m.get("neg_jerk"), TH["jerk_warn"], TH["jerk_bad"]))
        kpi("Shuffle", f"{m.get('fs','—')}<small> Hz</small>", "overrun ringdown", "warn" if m.get("fs") else "na")
        kpi("—", "—", "", "na")
        if m.get("neg_jerk") is not None and abs(m["neg_jerk"]) >= TH["jerk_warn"]:
            issue("Tip-out shunt", _sev(m["neg_jerk"], TH["jerk_warn"], TH["jerk_bad"]), f"{m['neg_jerk']} m/s²/s", "Abrupt negative torque on lift-off — head-nod / shunt.")
            act(1, "Soften tip-out torque path", "Rate-limit negative torque and manage lash crossing on overrun entry.")

    elif t in ("decel_coast", "decel_brake"):
        kpi("Decel rate", f"{m.get('decel_mean','—')}", "m/s² mean", "ok")
        kpi("Peak decel", f"{m.get('decel_peak','—')}", "m/s²", "ok")
        kpi("Disturbance", f"{m.get('disturb_pp','—')}", "m/s² p-p", _sev(m.get("disturb_pp"), TH["disturb_warn"], TH["disturb_bad"]))
        kpi("Jerk RMS", f"{m.get('jerk_rms','—')}", "m/s²/s" + (f" · {m['fs']} Hz" if m.get("fs") else ""), _sev(m.get("jerk_rms"), TH["jerk_warn"], TH["jerk_bad"]))
        if m.get("disturb_pp") is not None and _sev(m["disturb_pp"], TH["disturb_warn"], TH["disturb_bad"]) != "ok":
            issue("Deceleration disturbance", _sev(m["disturb_pp"], TH["disturb_warn"], TH["disturb_bad"]), f"{m['disturb_pp']} m/s²", "Decel is not smooth — surge/oscillation during the slowdown.")
            act(1, "Smooth deceleration", "Check overrun fuel cut-in/out, regen blend, and lash handling on the decel torque path.")

    elif t == "tip_in_cstspd":
        kpi("Response delay", f"{m.get('resp_ms','—')}<small> ms</small>", "tip-in → accel", _sev(m.get("resp_ms"), TH["resp_warn"], TH["resp_bad"]))
        kpi("Build rate", f"+{m.get('posg','—')}", "ax grad m/s²/s", _sev(m.get("posg"), TH["posg_warn"], TH["posg_bad"]))
        kpi("Peak ax", f"{m.get('ax_peak','—')}", "m/s²", "ok")
        kpi("Shuffle", f"{m.get('fs','—')}<small> Hz</small>", "tip-in ringdown", "warn" if m.get("fs") else "na")
        if m.get("resp_ms") is not None and _sev(m["resp_ms"], TH["resp_warn"], TH["resp_bad"]) != "ok":
            issue("Tip-in hesitation", _sev(m["resp_ms"], TH["resp_warn"], TH["resp_bad"]), f"{m['resp_ms']} ms", "Delay from pedal tip-in to acceleration at constant speed.")
            act(1, "Improve tip-in response", "Reduce torque-onset delay (air path / torque reserve); keep wheel-torque build prompt and linear.")

    elif t == "tip_out_cstspd":
        kpi("Decel ax", f"{m.get('ax_min','—')}", "m/s² lift-off", "ok")
        kpi("Neg jerk", f"{m.get('neg_jerk','—')}", "m/s²/s", _sev(m.get("neg_jerk"), TH["jerk_warn"], TH["jerk_bad"]))
        kpi("Shuffle", f"{m.get('fs','—')}<small> Hz</small>", "overrun ringdown", "warn" if m.get("fs") else "na")
        kpi("—", "—", "", "na")
        if m.get("neg_jerk") is not None and abs(m["neg_jerk"]) >= TH["jerk_warn"]:
            issue("Tip-out shunt", _sev(m["neg_jerk"], TH["jerk_warn"], TH["jerk_bad"]), f"{m['neg_jerk']} m/s²/s", "Abrupt negative torque on lift-off at constant speed — head-nod / shunt.")
            act(1, "Soften tip-out torque path", "Rate-limit negative torque and manage lash crossing on overrun entry.")

    elif t in ("engine_start", "engine_stop"):
        lbl = "start" if t == "engine_start" else "stop"
        kpi(f"Engine {lbl}", (f"{m.get('start_ms','—')}<small> ms</small>" if t == "engine_start" else "—"), ("cranking" if t == "engine_start" else "shutdown"), "ok")
        kpi("Body shake", f"{m.get('ax_pp','—')}", "m/s² p-p", _sev(m.get("ax_pp"), TH["shock_warn"], TH["shock_bad"]))
        kpi("Peak jerk", f"{m.get('jerk_peak','—')}", "m/s²/s", _sev(m.get("jerk_peak"), TH["jerk_warn"], TH["jerk_bad"]))
        kpi("—", "—", "", "na")
        if m.get("ax_pp") is not None and _sev(m["ax_pp"], TH["shock_warn"], TH["shock_bad"]) != "ok":
            issue(f"Engine {lbl} shudder", _sev(m["ax_pp"], TH["shock_warn"], TH["shock_bad"]), f"{m['ax_pp']} m/s²", f"Body disturbance during engine {lbl} — felt as a shake at standstill.")
            act(1, f"Refine engine {lbl}", "Tune crank/run-up (or run-down) torque profile and mount strategy to reduce the disturbance.")

    elif t == "idle":
        kpi("Idle shake", f"{m.get('idle_shake','—')}", "m/s² std", _sev(m.get("idle_shake"), 0.05, 0.12))
        kpi("ax p-p", f"{m.get('ax_pp','—')}", "m/s²", "ok")
        kpi("—", "—", "", "na"); kpi("—", "—", "", "na")
        if m.get("idle_shake") is not None and m["idle_shake"] >= 0.05:
            issue("Idle vibration", _sev(m["idle_shake"], 0.05, 0.12), f"{m['idle_shake']} m/s²", "Measurable body vibration at idle.")
            act(1, "Reduce idle vibration", "Check idle speed/combustion stability and mount tuning.")

    # Merge AVL Operation Modes Criteria — rated 0–10 vs program targets
    main, sub = avl_map.avl_for(ev)
    _, _, _, crit_rows = avl_map.scorecard(ev, m)
    odriv_issues = crit_mod.issues_from_criteria(crit_rows)
    odriv_actions = crit_mod.actions_from_criteria(crit_rows)
    existing_titles = {i["title"].lower() for i in issues}
    for oi in odriv_issues:
        if oi["title"].lower() not in existing_titles:
            issues.append(oi)
            existing_titles.add(oi["title"].lower())
    act_titles = {a["title"].lower() for a in actions}
    next_pri = max((a["priority"] for a in actions), default=0) + 1
    for oa in odriv_actions:
        if oa["title"].lower() not in act_titles:
            oa = dict(oa, priority=next_pri)
            actions.append(oa)
            act_titles.add(oa["title"].lower())
            next_pri += 1

    # Top KPI cards from highest-priority measured ODRIV criteria
    rated = [r for r in crit_rows if r.get("rating") is not None]
    rated.sort(key=lambda r: (r.get("driv") or 9))
    for r in rated[:2]:
        sub = f"target {r['t']:.1f} · warn {r['wl']:.1f}"
        if r.get("physical") is not None:
            sub += f" · {r['physical']} {r['unit']}"
        kpis.insert(0, {"k": r["criteria"], "v": f"{r['rating']:.1f}<small>/10</small>", "sub": sub, "sev": r["sev"]})

    worst = crit_mod.summarize_verdict(crit_rows)
    for i in issues:
        if i["severity"] == "bad":
            worst = "bad"; break
        if i["severity"] == "warn" and worst != "bad":
            worst = "warn"
    actions.sort(key=lambda a: a["priority"])
    while len(kpis) < 4:
        kpis.append({"k": "—", "v": "—", "sub": "", "sev": "na"})
    return issues, actions, worst, kpis[:4]
