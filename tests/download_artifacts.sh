#!/bin/bash
# Download ICRC ledger and indexer wasm files
set -e
cd "$(dirname "$0")"
mkdir -p artifacts

BASE_URL="https://github.com/dfinity/ic/releases/download/ledger-suite-icrc-2025-02-27"

echo "Downloading ledger..."
curl -sL -o artifacts/ledger.wasm.gz "${BASE_URL}/ic-icrc1-ledger.wasm.gz"
gunzip -f artifacts/ledger.wasm.gz
curl -sL -o artifacts/ledger.did "${BASE_URL}/ledger.did"

echo "Downloading indexer..."
curl -sL -o artifacts/indexer.wasm.gz "${BASE_URL}/ic-icrc1-index-ng.wasm.gz"
gunzip -f artifacts/indexer.wasm.gz
curl -sL -o artifacts/indexer.did "${BASE_URL}/index-ng.did"

echo "✅ Artifacts downloaded"
ls -la artifacts/
