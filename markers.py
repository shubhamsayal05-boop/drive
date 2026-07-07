"""Precise time-localization of drivability issues within a maneuver.

Each marker pins an issue (or a phase boundary) to an exact timestamp (or span)
on the recording's own time base, so the UI can show *when* something happened and
drive the vehicle animation to react only at those instants.

A marker = {t, t_end|None, kind, label, severity, f}
  kind:     delay | decision | execution | snatch | shock | shuffle | shunt |
            disturb | shake
  severity: bad | warn | info   (info = phase boundary, not a fault)
  f:        characteristic frequency (Hz) for the animation ring (shuffle)
"""
import numpy as np


def build(ev, sigs, m, issues):
    g = sigs.get("t")
    ax = sigs.get("ax_filt")
    if g is None or ax is None or len(g) < 4:
        return []
    dt = float(g[1] - g[0])
    jerk = np.gradient(ax, dt)
    ti = ev["t_trigger"]
    teng = ev["t_shift"]
    t = ev["type"]
    fs = m.get("fs")

    sev_pairs = [(i["title"].lower(), i["severity"]) for i in issues]

    def sev_for(*keys):
        for k in keys:
            for title, s in sev_pairs:
                if k in title:
                    return s
        return "info"

    def tpeak(t0, t1, sig, mode="absmax"):
        w = (g >= t0) & (g <= t1)
        idx = np.where(w)[0]
        if not len(idx):
            return None
        s = sig[idx]
        if mode == "max":
            j = int(np.argmax(s))
        elif mode == "min":
            j = int(np.argmin(s))
        else:
            j = int(np.argmax(np.abs(s)))
        return float(g[idx[j]])

    M = []

    def add(t0, kind, label, sev, t1=None, f=None):
        if t0 is None:
            return
        M.append({
            "t": round(float(t0), 3),
            "t_end": (round(float(t1), 3) if t1 is not None else None),
            "kind": kind, "label": label, "severity": sev,
            "f": float(f) if f else float(fs) if fs else 6.0,
        })

    if t in ("kickdown_downshift", "poweron_upshift"):
        if m.get("tax"):
            add(ti, "delay", "Response delay", sev_for("delay", "hesitation", "response"), t1=m["tax"])
        if m.get("tdec"):
            add(m["tdec"], "decision", "Shift decision", "info")
        add(teng, "execution", "Shift engagement", sev_for("execution", "duration", "shift"))
        add(tpeak(ti, ti + 1.8, jerk, "max"), "snatch", "Snatch (Ax gradient)", sev_for("snatch", "jerk", "gradient"))
        if t == "poweron_upshift":
            add(tpeak(teng - 0.2, teng + 0.4, jerk, "absmax"), "shock", "Upshift shock", sev_for("shock"))
        if fs:
            add(teng, "shuffle", f"Shuffle {fs} Hz", sev_for("shuffle", "oscill", "disturb"), t1=teng + 1.4, f=fs)

    elif t in ("drive_away", "drive_away_ess"):
        if m.get("launch_ms") is not None:
            add(ti, "delay", "Launch hesitation", sev_for("hesitation", "delay"), t1=ti + max(0.0, m["launch_ms"]) / 1000.0)
        add(tpeak(ti, ti + 2.5, jerk, "absmax"), "shock", "Launch jerk", sev_for("jerk", "snatch", "shock"))
        if fs:
            add(ti, "shuffle", f"Shuffle {fs} Hz", sev_for("shuffle", "disturb"), t1=ti + 1.4, f=fs)

    elif t in ("accel_constant_load", "accel_load_increase", "decel_coast", "decel_brake"):
        lo = ev["t0"] + 0.2
        hi = ev["t1"] - 0.2
        w = (g >= lo) & (g <= hi)
        idx = np.where(w)[0]
        if len(idx) > 4:
            trend = np.polyval(np.polyfit(g[idx], ax[idx], 1), g[idx])
            resid = ax[idx] - trend
            add(float(g[idx[int(np.argmax(np.abs(resid)))]]), "disturb", "Disturbance peak", sev_for("disturb"))
        if fs:
            add((ev["t0"] + ev["t1"]) / 2.0, "shuffle", f"Shuffle {fs} Hz", sev_for("disturb", "shuffle"), t1=hi, f=fs)

    elif t in ("tip_out_cstspd", "tip_out_overrun"):
        add(tpeak(ti, ti + 1.5, jerk, "min"), "shunt", "Tip-out shunt", sev_for("shunt", "tip-out"))
        if fs:
            add(ti, "shuffle", f"Shuffle {fs} Hz", sev_for("shuffle"), t1=ti + 1.4, f=fs)

    elif t == "tip_in_cstspd":
        if m.get("resp_ms") is not None:
            add(ti, "delay", "Response delay", sev_for("hesitation", "delay"), t1=ti + max(0.0, m["resp_ms"]) / 1000.0)
        add(tpeak(ti, ti + 1.6, jerk, "max"), "snatch", "Tip-in snatch", sev_for("snatch", "jerk"))

    elif t in ("engine_start", "engine_stop", "lever_change"):
        add(tpeak(ti - 0.5, ti + 1.5, jerk, "absmax"), "shock", "Engagement shake",
            sev_for("shudder", "shake", "vibration", "clunk"))

    elif t == "idle":
        add(tpeak(ev["t0"], ev["t1"], jerk, "absmax"), "shake", "Idle vibration", sev_for("vibration", "shake"))

    M.sort(key=lambda x: x["t"])
    return M
