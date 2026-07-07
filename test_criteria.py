#!/usr/bin/env python3
"""Smoke tests for Operation Modes Criteria (.edo) integration."""
import json
import struct
import tempfile
from pathlib import Path

from drivescope import edo_loader, criteria, sdv_map


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


def test_json_load():
    sample = {
        "(PT) KD - tip in downshift": [
            {"criteria": "Response delay", "t": 8.0, "wl": 7.6, "driv": 1},
            {"criteria": "Shock", "t": 7.9, "wl": 7.0, "driv": 2},
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sample, f)
        path = f.name
    crit = edo_loader.load(path)
    assert "(PT) KD - tip in downshift" in crit
    assert len(crit["(PT) KD - tip in downshift"]) == 2


def test_binary_edo_roundtrip():
    sample = {
        "Power-on upshift": [
            {"criteria": "Shift duration", "t": 8.0, "wl": 7.5, "driv": 1},
        ]
    }
    data = _make_edo(sample)
    crit = edo_loader.load_from_bytes(data)
    assert crit["Power-on upshift"][0]["criteria"] == "Shift duration"


def test_rating_and_verdict():
    metrics = {"tot_ms": 400, "exec_ms": 550, "posg": 28, "shock": 0.8}
    rows = criteria.evaluate_mode("(PT) KD - tip in downshift", metrics)
    rated = [r for r in rows if r["rating"] is not None]
    assert rated, "expected at least one rated criterion"
    assert criteria.summarize_verdict(rows) in ("ok", "warn", "bad")


def test_scorecard_integration():
    ev = {"type": "kickdown_downshift", "label": "KD"}
    m = {"tot_ms": 420, "exec_ms": 480, "dec_ms": 120, "posg": 22, "negg": -12, "shock": 0.7}
    name, group, rows = sdv_map.scorecard(ev, m)
    assert name == "(PT) KD - tip in downshift"
    assert any(r.get("rating") is not None for r in rows)


if __name__ == "__main__":
    test_json_load()
    test_binary_edo_roundtrip()
    test_rating_and_verdict()
    test_scorecard_integration()
    print("criteria tests OK")
