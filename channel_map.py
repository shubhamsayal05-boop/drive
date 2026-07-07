"""Configurable channel-name resolver.

Channel names differ across OEMs/programs, so the engine never hard-codes them.
A canonical signal (e.g. 'ax_filt') maps to an ordered list of regex candidates;
the first channel in the file that matches wins. Unmatched signals are reported
so the UI/CLI can surface them and the user can extend the config.
"""
import json, re
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).parent / "config" / "channels.json"


class ChannelMap:
    def __init__(self, config_path=None):
        cfg = json.loads(Path(config_path or DEFAULT_CONFIG).read_text())
        self.spec = cfg["signals"]
        self.resolved = {}      # canonical -> actual channel name
        self.unit_g = {}        # canonical -> bool (convert g->m/s^2)
        self.unresolved = []    # canonical names with no match

    def resolve(self, available_channels):
        """Match canonical signals against the channel names present in the file."""
        # prefer 'base' channel names (no backslash device suffix, no CAN-monitor dupes)
        def score(name):
            s = 0
            if "\\" in name: s += 10
            if "CAN" in name.upper(): s += 5
            return s
        chans = sorted(set(available_channels), key=score)
        for canon, meta in self.spec.items():
            hit = None
            for pat in meta["patterns"]:
                rx = re.compile(pat, re.IGNORECASE)
                for ch in chans:
                    if rx.search(ch):
                        hit = ch
                        break
                if hit:
                    break
            if hit:
                self.resolved[canon] = hit
                self.unit_g[canon] = bool(meta.get("unit_g"))
            else:
                self.unresolved.append(canon)
        return self.resolved

    def role(self, canon):
        return self.spec.get(canon, {}).get("role", canon)

    def has(self, canon):
        return canon in self.resolved
