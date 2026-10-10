#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Install Python 3.12+ and follow README.md to create .venv first.'
    exit 1
fi
exec .venv/bin/python server.py --profile core-hr "$@"
