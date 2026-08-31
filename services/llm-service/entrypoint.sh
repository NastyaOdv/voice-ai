#!/usr/bin/env sh
set -e
echo "[entrypoint] starting LLM worker..."
exec python main.py
