#!/usr/bin/env bash
# Wrapper: safe read of a secret file, prints only existence status
set -euo pipefail

op="$1"
shift

case "$op" in
  status)
    path="$1"
    if [ -f "$path" ]; then
      size=$(stat --format='%s' "$path" 2>/dev/null || echo "?")
      echo "EXISTS size=$size"
    elif [ -d "$path" ]; then
      count=$(find "$path" -type f 2>/dev/null | wc -l)
      echo "DIR count=$count"
    else
      echo "MISSING"
    fi
    ;;
  dup)
    src="$1"
    dst="$2"
    if [ ! -f "$src" ]; then
      echo "SKIP src_missing=$src"
      exit 0
    fi
    cp -a "$src" "$dst"
    echo "DUP_OK"
    ;;
  dupdir)
    src="$1"
    dst="$2"
    if [ ! -d "$src" ]; then
      echo "SKIP src_missing=$src"
      exit 0
    fi
    mkdir -p "$dst"
    find "$src" -type f -exec cp -a {} "$dst/" \;
    echo "DUP_OK dir=$(find "$dst" -type f | wc -l) files"
    ;;
esac
