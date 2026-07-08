#!/usr/bin/env python3
"""Smoke tests for AVL Operation Modes Criteria integration."""
import json
import struct
import tempfile
from pathlib import Path

from drivescope import edo_loader, criteria, avl_map, sdv_map


def _make_edo(modes: dict) -> bytes:
    buf = bytearray()
    buf += struct.pack("<II", 1, len(modes))
    for name, rows in modes.items():
        nb = name.encode("utf-8")
        buf += struct.pack("<I", len(nb)) + nb
        buf += struct.pack("<I", len(rows))
        for r in rows:
            cn = r["criteria"].encode("utf-8")
            buf += struct.pack("<I", len(cn)) + cn
            buf += struct.pack("<ffi", float(r["t"]), float(r["wl"]), int(r["driv"]))
    return bytes(buf)


def test_avl_hierarchy_load():
    avl = avl_map.catalog()
    assert "modes" in avl
    assert len(avl["modes"]) >= 20
    creep = avl_map.enabled_criteria("Drive away", "Creep")
    assert any(c["name"] == "Brake release bump" for c in creep)


def test_event_to_avl_mapping():
    ev = {"type": "kickdown_downshift", "label": "KD"}
    main, sub = avl_map.avl_for(ev)
    assert main == "Gear shift"
    assert sub == "Tip-in downshift"


def test_avl_scorecard():
    ev = {"type": "kickdown_downshift", "label": "KD"}
    m = {"tot_ms": 420, "exec_ms": 480, "dec_ms": 120, "posg": 22, "negg": -12, "shock": 0.7}
    main, sub, sdv, rows = avl_map.scorecard(ev, m)
    assert main == "Gear shift"
    assert len(rows) > 5
    assert all(r.get("enabled") for r in rows)
    rated = [r for r in rows if r["rating"] is not None]
    assert rated


def test_json_targets_load():
    sample = {
        "(PT) KD - tip in downshift": [
            {"criteria": "Response delay", "t": 8.0, "wl": 7.6, "driv": 1},
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sample, f)
        path = f.name
    crit = edo_loader.load(path)
    assert "(PT) KD - tip in downshift" in crit


def test_sdv_map_wrapper():
    ev = {"type": "drive_away", "label": "Launch"}
    m = {"launch_ms": 400, "jerk_peak": 10, "ax_peak": 2.5}
    name, group, rows = sdv_map.scorecard(ev, m)
    assert "Drive away" in name
    assert group == "Drive away"
    assert len(rows) > 0


if __name__ == "__main__":
    test_avl_hierarchy_load()
    test_event_to_avl_mapping()
    test_avl_scorecard()
    test_json_targets_load()
    test_sdv_map_wrapper()
    print("criteria tests OK")
