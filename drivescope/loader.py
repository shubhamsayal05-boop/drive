"""MDF loading + resampling onto a common time grid.

Handles INCA '.dat' (ASAM MDF 3.x) and MDF4. Text/enumerated channels
(e.g. gear as 'ForwardGear_5', TCC state strings) are decoded via raw values.
"""
import numpy as np
from asammdf import MDF

G = 9.80665


class Recording:
    def __init__(self, path, channel_map):
        self.path = str(path)
        self.mdf = MDF(self.path)
        self.cmap = channel_map
        self.cmap.resolve(list(self.mdf.channels_db.keys()))
        self._cache = {}

    # ---- raw channel access ----
    def _raw(self, name):
        s = self.mdf.get(name)
        v = np.asarray(s.samples)
        if v.dtype.kind in ("S", "U", "O"):           # text/enum -> numeric raw
            s = self.mdf.get(name, raw=True)
            v = np.asarray(s.samples, float)
        else:
            v = v.astype(float)
        t = np.asarray(s.timestamps, float)
        return t, v

    def channel(self, canon):
        """Return (t, v) for a canonical signal in engineering units (ax in m/s^2)."""
        if canon in self._cache:
            return self._cache[canon]
        if not self.cmap.has(canon):
            return None, None
        t, v = self._raw(self.cmap.resolved[canon])
        if self.cmap.unit_g.get(canon):
            v = v * G
        self._cache[canon] = (t, v)
        return t, v

    def duration(self):
        t, _ = self.channel("pedal")
        if t is None or len(t) == 0:
            for c in self.cmap.resolved:
                t, _ = self.channel(c)
                if t is not None and len(t) > 0:
                    break
        return (float(t[0]), float(t[-1])) if (t is not None and len(t) > 0) else (0.0, 0.0)

    def resample(self, canon, grid):
        t, v = self.channel(canon)
        if t is None or len(t) == 0 or len(v) == 0:
            return None
        if len(t) == 1:                       # single-sample channel -> hold constant
            return np.full_like(grid, float(v[0]), dtype=float)
        if np.any(np.diff(t) < 0):            # ensure ascending for np.interp
            order = np.argsort(t); t, v = t[order], v[order]
        return np.interp(grid, t, v)

    def window(self, t0, t1, dt=0.01, signals=None):
        """Resample requested canonical signals onto a uniform grid over [t0,t1]."""
        grid = np.arange(t0, t1, dt)
        signals = signals or list(self.cmap.resolved.keys())
        out = {"t": grid}
        for c in signals:
            r = self.resample(c, grid)
            if r is not None:
                out[c] = r
        return out
