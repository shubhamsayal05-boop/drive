"""Vehicle / plant configuration — mirrors the AVL-DRIVE vehicle and
operation-mode settings so DriveScope's detection thresholds and the HIL plant
model use the real vehicle parameters instead of generic defaults.

Persisted to ~/.drivescope/vehicle_config.json. Defaults below match the
MY27 2.0L JL EVO QG2 I4 X2 configuration.
"""
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".drivescope"
CONFIG_PATH = CONFIG_DIR / "vehicle_config.json"

DEFAULT = {
    "vehicle": {
        "name": "MY27 2.0L JL EVO QG2 I4 X2",
        "mass_kg": 2017,
        "payload_kg": 75,
        "drive": "RWD",
        "A0_N": 214.4,            # road-load: F = A0 + B0*v + C0*v^2  (v in kph)
        "B0_N_per_kph": 1.25,
        "C0_N_per_kph2": 0.066,
        "wheel_radius_m": 0.39,
        "tire": "245/75-17.0",
    },
    "engine": {
        "displacement_l": 2.0,
        "cylinders": 4,
        "aspiration": "Turbo",
        "fuel": "Gasoline",
        "max_power_kw": 239, "power_rpm": 5600,
        "max_torque_nm": 450, "torque_rpm": 4000,
        "idle_rpm": 750,
        "rev_limit_rpm": 6500,
    },
    "transmission": {
        "gears": 8,
        # kph at 1000 rpm per gear (used to infer ratio / driveline behaviour)
        "kph_per_1000rpm": [8.44, 12.63, 18.84, 23.82, 30.89, 39.71, 47.33, 59.58],
        "tcc_open": 0, "tcc_locked": 1, "tcc_slip": 2,
    },
    "thresholds": {                 # AVL-DRIVE operation-mode detection
        "zero_speed_kph": 1.0,
        "zero_pedal_pct": 1.0,
        "full_load_pedal_pct": 98.0,
        "kickdown_pedal_pct": 98.0,
        "tip_rate_pct_s": 200.0,
        "decel_brake_pct": 3.0,
        "rolling_start_lower_kph": 12.0,
        "rolling_start_delta_kph": 10.0,
        "hill_start_grad_pct": 5.0,
        "transition_const_rpm": 891.0,
        "transition_const_kph": 11.0,
        "highest_creeping_gear": 2,
    },
    "signal_cal": {
        "pedal_released": 0.0, "pedal_full": 100.0,
        "brake_free_travel_pct": 3.0, "brake_full": 84.5,
        "gear_reverse_value": 11.0,
        "lever_P": 0, "lever_R": 1, "lever_N": 2, "lever_D": 4,
    },
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return _merge(DEFAULT, saved)
    except Exception:
        return json.loads(json.dumps(DEFAULT))   # deep copy of defaults


def save(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = _merge(DEFAULT, cfg)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
