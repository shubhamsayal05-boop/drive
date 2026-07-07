#!/usr/bin/env bash
# Start the DriveScope web app, then open http://localhost:8000
set -e
python3 -m pip install -r requirements.txt
exec uvicorn drivescope.api:app --host 0.0.0.0 --port 8000 --reload
