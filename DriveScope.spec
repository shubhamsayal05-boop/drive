# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ["asammdf", "numpy", "uvicorn", "fastapi", "starlette",
            "anyio", "h11", "click", "multipart"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# bundle ALL drivescope submodules explicitly (relative imports aren't auto-traced)
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "drivescope", "drivescope.api", "drivescope.engine", "drivescope.events",
    "drivescope.metrics", "drivescope.diagnostics", "drivescope.sdv_map",
    "drivescope.channel_map", "drivescope.loader", "drivescope.report", "drivescope.cli",
]

# web assets + channel/SDV config (config/*.json must ship inside the exe)
datas += [
    ("frontend", "frontend"),
    ("drivescope/config", "drivescope/config"),
    ("drivescope", "drivescope"),   # ship the package source so submodule import always resolves
]

a = Analysis(["launch.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DriveScope",
          console=True, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="DriveScope")
