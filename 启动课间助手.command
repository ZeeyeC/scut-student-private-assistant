#!/bin/sh
set -eu
cd "$(dirname "$0")"
if /bin/bash scripts/initialize-macos.sh "$@"; then
  exit 0
else
  status=$?
  printf '%s\n' '启动或初始化失败，请查看上方报错及 .tools/macos-initialize.log。'
  if [ -t 0 ]; then
    printf '%s' '按回车关闭窗口。'
    read -r answer || true
  fi
  exit "$status"
fi
