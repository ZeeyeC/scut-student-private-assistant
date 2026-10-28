#!/bin/bash
set -eu
cd "$(dirname "$0")"
version=$(tr -d '[:space:]' < VERSION)
release="../../Demo${version%.0}/课间桌宠.app"
if [ -x "$release/Contents/MacOS/CampusPet" ]; then
  open "$release"
  exit 0
fi
if [ ! -x 'dist/课间桌宠.app/Contents/MacOS/CampusPet' ]; then
  ../backend/.venv/bin/python build.py
fi
open 'dist/课间桌宠.app'
