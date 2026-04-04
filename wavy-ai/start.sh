#!/usr/bin/env bash
# Start the Wavy Labs AI backend
# Usage: ./start.sh [--port 5555] [--log-level INFO]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
exec python server.py "$@"
