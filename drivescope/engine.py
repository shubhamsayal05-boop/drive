"""Orchestrator: .dat file -> structured multi-event diagnostic result."""
import numpy as np
from .channel_map import ChannelMap
from .loader import Recording
from . import events as ev_mod
from . import metrics as met
from . import diagnostics as diag
from . import sdv_map
from . import edo_loader
from . import markers as mk_mod

LANE_SIGNALS = ["ax_filt", "ax_raw", "pedal", "gear_act", "gear_tgt",
                "engine_speed", "turbine_speed", "eng_trq", "vehicle_speed"]


def _ds(sigs, step=2):
    return {k: np.round(np.asarray(v, float)[::step], 3).tolist() for k, v in sigs.items()}


def analyze(path, channel_config=None, max_events=24, vehicle_cfg=None):
    from . import vehicle as veh_cfg_mod
    vcfg = vehicle_cfg if vehicle_cfg is not None else veh_cfg_mod.load()
    edo_loader.load()
    cmap = ChannelMap(channel_config)
    rec = Recording(path, cmap)
    t0, t1 = rec.duration()

    detected = ev_mod.detect(rec, max_events=max_events, cfg=vcfg)
    # focus to the tested maneuver family (collector-name aware), keep all as fallback
    hint = ev_mod.maneuver_hint(path)
    if hint:
        focused = [e for e in detected if e["type"] in hint]
        if focused:
            detected = focused
    results = []
    for i, ev in enumerate(detected):
        sigs, m = met.compute(rec, ev)
        issues, actions, verdict, kpis = diag.diagnose(ev, m)
        sdv_name, sdv_group, criteria = sdv_map.scorecard(ev, m)
        evt_markers = mk_mod.build(ev, sigs, m, issues)
        keep = ["t"] + [s for s in LANE_SIGNALS if s in sigs]
        sub = {k: sigs[k] for k in keep}
        if "az_raw" in sigs:
            sub["az_raw"] = sigs["az_raw"]
        results.append({
            "id": i, "type": ev["type"], "label": ev["label"],
            "sdv": sdv_name, "group": sdv_group, "criteria": criteria,
            "window": {"t0": round(ev["t0"], 2), "t1": round(ev["t1"], 2)},
            "trigger": round(ev["t_trigger"], 2), "shift": round(ev["t_shift"], 2),
            "verdict": verdict, "kpis": kpis, "metrics": m,
            "issues": issues, "actions": actions, "markers": evt_markers, "signals": _ds(sub),
        })

    # group counts by type for a quick overview
    by_type = {}
    for e in results:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    debug = ev_mod.summarize(rec) if not results else None

    crit_meta = {"source": edo_loader.active_source(), "warning": edo_loader.load_warning()}

    return {
        "file": str(path), "duration": [round(t0, 2), round(t1, 2)],
        "channels_resolved": cmap.resolved, "channels_unresolved": cmap.unresolved,
        "roles": {c: cmap.role(c) for c in cmap.resolved},
        "n_events": len(results), "by_type": by_type, "events": results,
        "debug": debug,
        "vehicle_config": vcfg,
        "criteria": crit_meta,
    }
