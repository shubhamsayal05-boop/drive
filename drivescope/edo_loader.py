"""Load AVL-DRIVE / ODRIV Operation Modes Criteria.

Supports:
  - Native ``.edo`` binary export (ODRIV Target Wizard / Operation Modes Criteria)
  - JSON sidecar with the same schema as ``sdv_criteria.json``
  - Bundled ``config/sdv_criteria.json`` fallback

The binary layout (version 1) is::

    uint32  version          (1)
    uint32  n_modes
    repeat n_modes:
        uint32  name_byte_len
        bytes   name_utf8
        uint32  n_criteria
        repeat n_criteria:
            uint32  name_byte_len
            bytes   name_utf8
            float32 target      (AVL rating 0–10)
            float32 warn_limit
            uint32  driv_priority
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

CFG = Path(__file__).parent / "config"
DEFAULT_JSON = CFG / "sdv_criteria.json"
DEFAULT_EDO = CFG / "Operation modes criteria.edo"

_loaded_path: Path | None = None
_loaded: dict | None = None
_load_warning: str | None = None


def load_warning() -> str | None:
    return _load_warning


class EdoParseError(ValueError):
    pass


def _read_cstr_pair(data: bytes, off: int):
    if off + 4 > len(data):
        raise EdoParseError("unexpected end of .edo file")
    n = struct.unpack_from("<I", data, off)[0]
    off += 4
    if n > 10_000_000 or off + n > len(data):
        raise EdoParseError(f"invalid string length {n} at offset {off - 4}")
    name = data[off:off + n].decode("utf-8", errors="replace")
    return name, off + n


def parse_edo_binary(data: bytes) -> dict:
    if len(data) < 8:
        raise EdoParseError(f".edo file too small ({len(data)} bytes) — export may be corrupt")
    version, n_modes = struct.unpack_from("<II", data, 0)
    if version != 1:
        raise EdoParseError(f"unsupported .edo version {version} (expected 1)")
    if n_modes == 0xFFFFFFFF:
        raise EdoParseError(".edo export is empty (n_modes = -1) — re-export from ODRIV/AVL-DRIVE")
    if n_modes > 500:
        raise EdoParseError(f"unreasonable mode count {n_modes}")
    off = 8
    out: dict = {}
    for _ in range(n_modes):
        mode_name, off = _read_cstr_pair(data, off)
        if off + 4 > len(data):
            raise EdoParseError("truncated .edo at criteria count")
        n_crit = struct.unpack_from("<I", data, off)[0]
        off += 4
        rows = []
        for _ in range(n_crit):
            cname, off = _read_cstr_pair(data, off)
            if off + 12 > len(data):
                raise EdoParseError("truncated .edo at criterion targets")
            t, wl, driv = struct.unpack_from("<ffi", data, off)
            off += 12
            rows.append({"criteria": cname, "t": round(t, 2), "wl": round(wl, 2), "driv": int(driv)})
        out[mode_name] = rows
    return out


def _parse_text(data: bytes) -> dict:
    text = data.decode("utf-8-sig").strip()
    if not text:
        raise EdoParseError("empty criteria file")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise EdoParseError("criteria JSON must be an object keyed by operation-mode name")
    return _normalize(obj)


def _normalize(raw: dict) -> dict:
    out = {}
    for mode, rows in raw.items():
        if not isinstance(rows, list):
            continue
        norm = []
        for r in rows:
            if not isinstance(r, dict) or "criteria" not in r:
                continue
            norm.append({
                "criteria": str(r["criteria"]),
                "t": float(r.get("t", r.get("target", 0))),
                "wl": float(r.get("wl", r.get("warn_limit", r.get("warn", 0)))),
                "driv": int(r.get("driv", r.get("priority", 9))),
            })
        if norm:
            out[str(mode)] = norm
    return out


def load_from_bytes(data: bytes, source: str = "upload") -> dict:
    if not data:
        raise EdoParseError("empty file")
    if data[:1] in (b"{", b"[") or data[:3] == b"\xef\xbb\xbf{":
        return _parse_text(data)
    try:
        return parse_edo_binary(data)
    except EdoParseError:
        raise
    except struct.error as e:
        raise EdoParseError(f"binary .edo parse failed: {e}") from e


def load(path: str | Path | None = None) -> dict:
    """Return {operation_mode: [{criteria, t, wl, driv}, ...]}."""
    global _loaded, _loaded_path, _load_warning
    _load_warning = None
    candidates = []
    if path:
        candidates.append(Path(path))
    else:
        candidates.extend([DEFAULT_EDO, DEFAULT_JSON])

    last_err = None
    edo_failed = False
    for p in candidates:
        if not p.exists():
            continue
        try:
            data = p.read_bytes()
            if p.suffix.lower() == ".json":
                crit = _normalize(json.loads(data.decode("utf-8")))
            else:
                try:
                    crit = load_from_bytes(data, source=str(p))
                except EdoParseError as e:
                    if p.suffix.lower() == ".edo":
                        edo_failed = True
                        last_err = e
                        continue
                    raise
            if not crit:
                raise EdoParseError(f"no criteria rows in {p.name}")
            _loaded, _loaded_path = crit, p
            if edo_failed and p.suffix.lower() == ".json":
                _load_warning = (
                    f"{last_err} — using bundled sdv_criteria.json. "
                    "Re-export Operation Modes Criteria from ODRIV/AVL-DRIVE and upload via Criteria (.edo)."
                )
            return crit
        except (EdoParseError, json.JSONDecodeError, OSError) as e:
            last_err = e
            continue

    if DEFAULT_JSON.exists():
        crit = _normalize(json.loads(DEFAULT_JSON.read_text(encoding="utf-8")))
        _loaded, _loaded_path = crit, DEFAULT_JSON
        if edo_failed:
            _load_warning = (
                f"{last_err} — using bundled sdv_criteria.json. "
                "Re-export Operation Modes Criteria from ODRIV/AVL-DRIVE and upload via Criteria (.edo)."
            )
        return crit
    raise EdoParseError(f"could not load operation-mode criteria: {last_err}")


def active_source() -> str:
    return str(_loaded_path or DEFAULT_JSON)


def reload(path: str | Path | None = None) -> dict:
    global _loaded, _loaded_path
    _loaded = None
    _loaded_path = None
    return load(path)


def save_json(criteria: dict, path: str | Path | None = None) -> Path:
    dest = Path(path or DEFAULT_JSON)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(criteria, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
