#!/bin/bash
# Alfred deploy — run on ANY machine with the Core2 plugged in (Linux/macOS/WSL).
# Syncs code from GitHub, then pushes main.py to the device over USB.
# One-time setup: pip install mpremote
set -e
cd "$(dirname "$0")"

echo "[1/3] git pull..."
git pull --rebase || echo "(pull failed — continuing with local copy)"

echo "[2/3] deploying main.py to Core2 over USB..."
PORT=${1:-auto}
if [ "$PORT" = "auto" ]; then
  python3 -m mpremote connect /dev/ttyACM0 resume cp tools/uiflow/main.py :main.py || \
  python3 -m mpremote cp tools/uiflow/main.py :main.py
else
  python3 -m mpremote connect "$PORT" resume cp tools/uiflow/main.py :main.py
fi

echo "[3/3] rebooting device..."
python3 -m mpremote connect /dev/ttyACM0 reset 2>/dev/null || python3 -m mpremote reset 2>/dev/null || true

echo "done — watch the screen."
