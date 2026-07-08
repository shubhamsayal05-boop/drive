"""Per-maneuver drivability metrics, computed from measured channels only."""
import numpy as np

trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


def _grad(x, dt): return np.gradient(x, dt)


def _onset(grid, ax, t_from, thr=0.5):
    on = np.where((grid > t_from) & (ax > thr))[0]
    return float(grid[on[0]]) if len(on) else None


def _disturb_pp(grid, ax, t0, t1):
    """Peak-to-peak residual acceleration after detrending."""
    seg = (grid >= t0) & (grid <= t1)
    if seg.sum() < 6:
        return None, None
    gw = grid[seg]; axw = ax[seg]
    trend = np.polyval(np.polyfit(gw, axw, 1), gw)
    resid = axw - trend
    pp = float(np.ptp(resid))
    cov = float(np.std(resid) / (abs(np.mean(axw)) + 1e-6))
    lin = float(max(0, 100 * (1 - cov)))
    return round(pp, 2), round(lin, 1)


def _launch_metrics(g, ax, ped, rpm, veh, ti, dt, t_ped, tax):
    """Extended drive-away / standing-start metrics for AVL criteria scorecard."""
    m = {}
    w = (g >= ti) & (g <= ti + 2.5)
    w_build = (g >= ti) & (g <= ti + 1.8)
    w_eng = (g >= ti) & (g <= ti + 0.5)
    dax = _grad(ax, dt)

    if tax is not None and t_ped is not None:
        delay = max(0.0, (tax - t_ped) * 1000)
        m["launch_ms"] = round(delay, 0)
        m["tot_ms"] = round(delay, 0)
        m["resp_ms"] = round(delay, 0)
    else:
        m["launch_ms"] = None
        m["tot_ms"] = None
        m["resp_ms"] = None

    m["ax_peak"] = round(float(np.nanmax(ax[w])), 2)
    m["ax_mean"] = round(float(np.nanmean(ax[w_build])), 2)
    m["jerk_peak"] = round(float(np.nanmax(np.abs(dax[w]))), 1)
    m["engage_jerk"] = m["jerk_peak"]
    m["posg"] = round(float(np.nanmax(dax[w_build])), 1)
    m["negg"] = round(float(np.nanmin(dax[w_build])), 1)
    m["neg_jerk"] = round(float(np.nanmin(dax[w])), 1)

    if w_eng.sum() > 3:
        m["ax_pp"] = round(float(np.ptp(ax[w_eng])), 2)
        m["shock"] = round(float(np.nanmax(ax[w_eng]) - np.nanmin(ax[w_eng])), 2)

    if tax is not None:
        t_pull = float(tax)
        pp, lin = _disturb_pp(g, ax, t_pull, min(t_pull + 1.5, float(g[-1])))
        if pp is not None:
            m["disturb_pp"] = pp
            m["linearity_pct"] = lin

    fs = _shuffle(g, ax, ti, ti + 1.5)
    if fs is not None:
        m["fs"] = round(fs, 2)

    if ped is not None:
        on = np.where((g >= ti - 0.6) & (ped > 5))[0]
        if len(on):
            m["pedal_at_launch"] = round(float(ped[on[0]]), 0)
        m["pedal_mean"] = round(float(np.nanmean(ped[(g >= ti) & (g <= ti + 1.0)])), 0)

    if rpm is not None:
        wr = (g >= ti - 0.3) & (g <= ti + 2.5)
        m["rpm_start"] = round(float(rpm[np.argmin(np.abs(g - ti))]))
        m["rpm_peak"] = round(float(np.nanmax(rpm[wr])))
        m["rpm_min"] = round(float(np.nanmin(rpm[wr])), 0)
        pre = (g >= ti - 1.0) & (g < ti)
        post = (g >= ti) & (g <= ti + 1.2)
        if pre.sum() > 2 and post.sum() > 2:
            m["rpm_drop"] = round(float(np.nanmedian(rpm[pre])) - float(np.nanmin(rpm[post])), 0)

    if veh is not None:
        hit = np.where((g >= ti) & (veh >= 10))[0]
        if len(hit):
            m["t_to_10kph_ms"] = round((g[hit[0]] - ti) * 1000)

    return m


def _shuffle(grid, ax, t0, t1):
    seg = (grid >= t0) & (grid <= t1)
    if seg.sum() < 8:
        return None
    y = ax[seg] - np.polyval(np.polyfit(grid[seg], ax[seg], 2), grid[seg])
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    ff = np.fft.rfftfreq(len(y), grid[1] - grid[0])
    return float(ff[1 + int(np.argmax(Y[1:]))]) if len(Y) > 2 else None


def compute(rec, ev, dt=0.01):
    sigs = rec.window(ev["t0"], ev["t1"], dt)
    g = sigs["t"]
    ax = sigs.get("ax_filt"); axr = sigs.get("ax_raw")
    ped = sigs.get("pedal"); gear = sigs.get("gear_act"); gtgt = sigs.get("gear_tgt")
    rpm = sigs.get("engine_speed"); veh = sigs.get("vehicle_speed")
    ti = ev["t_trigger"]
    m = {"ti": round(ti, 2), "teng": round(ev["t_shift"], 2), "has_shift": False}
    t = ev["type"]

    if t in ("kickdown_downshift", "poweron_upshift"):
        m["has_shift"] = True
        teng = ev["t_shift"]
        if gtgt is not None and ev.get("gear_to") is not None:
            idx = np.where(np.abs(np.round(gtgt) - ev["gear_to"]) < 0.5)[0]
            idx = idx[(g[idx] >= ti - 0.3) & (g[idx] <= ti + 2.0)]
            m["tdec"] = round(float(g[idx[0]]), 2) if len(idx) else None
        else:
            m["tdec"] = None
        if ax is not None:
            if t == "kickdown_downshift":
                tax = _onset(g, ax, ti, 0.5)
                m["tax"] = round(tax, 2) if tax else None
                m["tot_ms"] = round((tax - ti) * 1000) if tax else None
            dax = _grad(ax, dt); w = (g >= ti) & (g <= ti + 1.8)
            m["posg"] = round(float(np.nanmax(dax[w])), 1)
            m["negg"] = round(float(np.nanmin(dax[w])), 1)
            m["ax_peak"] = round(float(np.nanmax(ax[w])), 2)
            fs = _shuffle(g, ax, teng - 0.1, teng + 1.6); m["fs"] = round(fs, 2) if fs else None
            if t == "poweron_upshift":
                seg = (g >= teng - 0.2) & (g <= teng + 0.4)
                if seg.sum() > 3:
                    m["shock"] = round(float(np.nanmax(ax[seg]) - np.nanmin(ax[seg])), 2)
        if axr is not None:
            dr = _grad(axr, dt); w = (g >= ti) & (g <= ti + 1.8)
            m["posg_r"] = round(float(np.nanmax(dr[w])), 1)
            m["negg_r"] = round(float(np.nanmin(dr[w])), 1)
        if m.get("tdec") is not None:
            m["dec_ms"] = round((m["tdec"] - ti) * 1000); m["exec_ms"] = round((teng - m["tdec"]) * 1000)
        else:
            m["dec_ms"] = None; m["exec_ms"] = round((teng - ti) * 1000)
        if rpm is not None:
            w = (g >= ti) & (g <= ti + 2.0)
            m["rpm_start"] = round(float(rpm[np.argmin(np.abs(g - ti))]))
            m["rpm_peak"] = round(float(np.nanmax(rpm[w])))

    elif t in ("drive_away", "drive_away_ess"):
        if ped is not None:
            on = np.where((g >= ti - 0.6) & (ped > 15))[0]
            t_ped = float(g[on[0]]) if len(on) else ti
        else:
            t_ped = ti
        tax = _onset(g, ax, t_ped - 0.05, 0.4) if ax is not None else None
        if ax is not None:
            m.update(_launch_metrics(g, ax, ped, rpm, veh, ti, dt, t_ped, tax))
        if t == "drive_away_ess" and rpm is not None:
            pre = (g >= ti - 3.0) & (g <= ti)
            offs = np.where(pre & (rpm < 100))[0]
            ons = np.where((g > (g[offs[-1]] if len(offs) else ti - 3)) & (rpm > 500))[0]
            if len(offs) and len(ons):
                m["restart_ms"] = round((g[ons[0]] - g[offs[-1]]) * 1000)

    elif t in ("accel_constant_load", "accel_load_increase"):
        if ax is not None:
            w = (g >= ev["t0"] + 0.2) & (g <= ev["t1"] - 0.2)
            axw = ax[w]; gw = g[w]
            trend = np.polyval(np.polyfit(gw, axw, 1), gw)
            resid = axw - trend
            m["ax_mean"] = round(float(np.mean(axw)), 2)
            m["ax_std"] = round(float(np.std(axw)), 3)
            m["disturb_pp"] = round(float(np.ptp(resid)), 2)          # peak-to-peak disturbance
            m["jerk_rms"] = round(float(np.sqrt(np.mean(_grad(axw, dt) ** 2))), 1)
            fs = _shuffle(g, ax, ev["t0"] + 0.2, ev["t1"] - 0.2); m["fs"] = round(fs, 2) if fs else None
            cov = np.std(resid) / (abs(np.mean(axw)) + 1e-6)
            m["linearity_pct"] = round(float(max(0, 100 * (1 - cov))), 1)  # 100 = perfectly smooth
        if ped is not None:
            w = (g >= ev["t0"]) & (g <= ev["t1"])
            m["pedal_mean"] = round(float(np.mean(ped[w])), 0)

    elif t == "lever_change":
        if ax is not None:
            w = (g >= ti - 0.5) & (g <= ti + 1.5)
            m["engage_jerk"] = round(float(np.nanmax(np.abs(_grad(ax, dt)[w]))), 1)
            m["ax_pp"] = round(float(np.ptp(ax[w])), 2)
            fs = _shuffle(g, ax, ti, ti + 1.5); m["fs"] = round(fs, 2) if fs else None

    elif t == "tip_out_overrun":
        if ax is not None:
            w = (g >= ti) & (g <= ti + 1.5)
            m["ax_min"] = round(float(np.nanmin(ax[w])), 2)
            m["neg_jerk"] = round(float(np.nanmin(_grad(ax, dt)[w])), 1)
            fs = _shuffle(g, ax, ti, ti + 1.5); m["fs"] = round(fs, 2) if fs else None

    elif t in ("decel_coast", "decel_brake"):
        if ax is not None:
            w = (g >= ev["t0"] + 0.1) & (g <= ev["t1"] - 0.1)
            axw = ax[w]
            m["decel_mean"] = round(float(np.mean(axw)), 2)
            m["decel_peak"] = round(float(np.nanmin(axw)), 2)
            trend = np.polyval(np.polyfit(g[w], axw, 1), g[w])
            m["disturb_pp"] = round(float(np.ptp(axw - trend)), 2)
            m["jerk_rms"] = round(float(np.sqrt(np.mean(_grad(axw, dt) ** 2))), 1)
            fs = _shuffle(g, ax, ev["t0"] + 0.1, ev["t1"] - 0.1); m["fs"] = round(fs, 2) if fs else None

    elif t == "tip_in_cstspd":
        if ax is not None:
            tax = _onset(g, ax, ti, 0.5)
            m["resp_ms"] = round((tax - ti) * 1000) if tax else None
            dax = _grad(ax, dt); w = (g >= ti) & (g <= ti + 1.6)
            m["posg"] = round(float(np.nanmax(dax[w])), 1)
            m["ax_peak"] = round(float(np.nanmax(ax[w])), 2)
            fs = _shuffle(g, ax, ti, ti + 1.5); m["fs"] = round(fs, 2) if fs else None

    elif t == "tip_out_cstspd":
        if ax is not None:
            w = (g >= ti) & (g <= ti + 1.5)
            m["ax_min"] = round(float(np.nanmin(ax[w])), 2)
            m["neg_jerk"] = round(float(np.nanmin(_grad(ax, dt)[w])), 1)
            fs = _shuffle(g, ax, ti, ti + 1.5); m["fs"] = round(fs, 2) if fs else None

    elif t in ("engine_start", "engine_stop"):
        if ax is not None:
            w = (g >= ti - 0.5) & (g <= ti + 1.5)
            m["ax_pp"] = round(float(np.ptp(ax[w])), 2)
            m["jerk_peak"] = round(float(np.nanmax(np.abs(_grad(ax, dt)[w]))), 1)
        if rpm is not None and t == "engine_start":
            up = np.where((g > ti - 0.5) & (rpm > 500))[0]
            dn = np.where((g < ti) & (rpm < 100))[0]
            if len(up) and len(dn):
                m["start_ms"] = round((g[up[0]] - g[dn[-1]]) * 1000)

    elif t == "idle":
        if ax is not None:
            w = (g >= ev["t0"]) & (g <= ev["t1"])
            m["idle_shake"] = round(float(np.std(ax[w])), 3)
            m["ax_pp"] = round(float(np.ptp(ax[w])), 2)

    return sigs, m
