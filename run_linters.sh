#!/bin/bash
# Usage: ./run_linters.sh [--fix]
set -e

if [ "$1" = "--fix" ]; then
    echo "Fixing..."
    ruff check src/ tests/ --fix
    black src/ tests/
else
    echo "Checking..."
    ruff check src/ tests/
    black --check src/ tests/
fi
echo "✅ All linters passed!"
