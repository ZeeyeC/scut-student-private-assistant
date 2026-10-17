#!/bin/bash
set -eu
cd "$(dirname "$0")"
if [ ! -x 'dist/课间桌宠.app/Contents/MacOS/CampusPet' ]; then
  ../backend/.venv/bin/python build.py
fi
open 'dist/课间桌宠.app'
