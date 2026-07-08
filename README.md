# DriveScope

Automatic drivability diagnosis from INCA `.dat` / ASAM-MDF recordings.

Upload a recording → DriveScope auto-detects shift events (tip-in/kick-down
downshifts and power-on upshifts), computes the objective drivability metrics,
scores the issues, and proposes prioritised calibration actions — with an
interactive multi-channel scope you can scrub.

> Built for calibration / drivability / benchmark engineers. Diagnosis is
> read-only on measured data; no model is simulated.

---

## What it does

- **Auto channel mapping** — canonical signals (ax, engine/turbine speed, pedal,
  actual & target gear, torque, vehicle speed …) are resolved from the file by
  configurable regex patterns. Works across OEMs/programs by editing one JSON.
- **Event detection (operation modes)** — automatically finds and classifies:
  drive-away (launch), drive-away with **ESS** (engine stop-start restart),
  **acceleration constant load**, acceleration load increase, kick-down / tip-in
  downshift, power-on upshift, and tip-out / overrun. Uses recorded standstill /
  stop-start flags when present, derives from speed/pedal/gear otherwise.
- **Metrics (measured)** — response delay, **decision vs. execution latency
  split**, ax engagement gradient (filtered & raw), driveline shuffle frequency
  (FFT), engagement shock, engine flare.
- **Diagnosis + actions** — transparent, editable threshold rules turn metrics
  into severity-rated issues and prioritised calibration suggestions, with the
  measured numbers injected into each explanation.
- **Dashboard** — KPI cards, animated vehicle, stacked real-unit scope with
  phase bands + the gear-target-vs-actual gap that *is* the hesitation,
  scorecard, and actions. Drag the scope to scrub; the cursor reads all channels.

## Architecture

```
drivescope/
  channel_map.py   configurable canonical-signal resolver
  loader.py        MDF load + resample (handles text/enum channels)
  events.py        event detection & classification
  metrics.py       drivability metrics
  criteria.py      Operation Modes Criteria rating engine
  edo_loader.py    .edo / JSON criteria loader
  diagnostics.py   threshold rules -> issues + actions  (tune here)
  engine.py        orchestrator: file -> JSON result
  report.py        standalone offline HTML report (CLI)
  cli.py           command-line interface
  api.py           FastAPI: upload UI + /api/analyze
  config/channels.json   channel-name patterns (edit per program)
  config/sdv_criteria.json   ODRIV criteria targets (from .edo)
frontend/
  index.html  styles.css  app.js   (single renderer; used by web app + report)
```

## Install & run

```bash
pip install -r requirements.txt

# Web app  ->  open http://localhost:8000
./run.sh
#   or:  uvicorn drivescope.api:app --port 8000

# CLI (standalone offline report)
python -m drivescope.cli analyze path/to/recording.dat -o report.html
#   options: --json out.json   --channels my_channels.json   --max-events N
```

## Adapting to a different program / OEM

Channel names differ between recordings. If something shows as *unresolved*,
copy `drivescope/config/channels.json`, add the file's actual channel name (or a
regex) to the relevant signal's `patterns`, and pass `--channels my.json`
(CLI) — or replace the default config. `ax_*` channels flagged `unit_g` are
auto-converted g → m/s².

## Tuning the diagnosis

Severity thresholds and the suggestion text live in `diagnostics.py` (`TH`
dict + rules). They are intentionally explicit so a calibrator can align them to
program targets.

**Operation Modes Criteria (`.edo`)** — targets and warn limits per maneuver are
loaded from `drivescope/config/Operation modes criteria.edo` (ODRIV / AVL-DRIVE
export) with fallback to `sdv_criteria.json`. DriveScope maps measured signals to
approximate 0–10 ODRIV ratings and compares them to your program targets. Upload
a fresh `.edo` via **Criteria (.edo)** on the web UI or `POST /api/criteria`.

If the bundled `.edo` is corrupt or empty, re-export from ODRIV Target Wizard and
upload the file again.

## Honest limitations (read before trusting a number)

- **Metrics are first-order** estimators, not a re-implementation of AVL-DRIVE's
  internal criteria. AVL's gradient/disturbance figures use proprietary
  band-limited channels and detection windows, so absolute values differ
  (DriveScope reports both filtered and raw ax gradients for this reason).
- **Shuffle frequency** depends on the analysis window; confirm against a longer
  ring-down where possible.
- **Engagement time** uses the actual-gear signal; on some programs that flag
  lags true torque handover — cross-check with clutch/slip channels.
- Upshift shock/`tdec` for steady upshifts are coarse and shown for orientation.

Treat the output as a fast triage + visualisation layer that points the
calibrator at the right channels and the right calibration levers — not as a
certified scoring tool.
