#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x "dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion" ]; then
  exec "dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion" --data-dir "$PWD" --project
fi
if [ -x backend/.venv/bin/python ]; then
  exec backend/.venv/bin/python scripts/start-local.py
fi
printf '%s\n' '尚未构建桌面包，请先按 README 完成一次构建。'
read -r answer
