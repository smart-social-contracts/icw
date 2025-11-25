#!/bin/bash
# Download ICRC ledger and indexer wasm files
set -e
cd "$(dirname "$0")"
mkdir -p artifacts

LEDGER_URL="https://download.dfinity.systems/ic/d87954601e4b22972899e9957e800406a0a6b929/canisters/ic-icrc1-ledger.wasm.gz"
INDEXER_URL="https://download.dfinity.systems/ic/d87954601e4b22972899e9957e800406a0a6b929/canisters/ic-icrc1-index-ng.wasm.gz"
LEDGER_DID="https://raw.githubusercontent.com/dfinity/ic/d87954601e4b22972899e9957e800406a0a6b929/rs/ledger_suite/icrc1/ledger/ledger.did"
INDEXER_DID="https://raw.githubusercontent.com/dfinity/ic/d87954601e4b22972899e9957e800406a0a6b929/rs/ledger_suite/icrc1/index-ng/index-ng.did"

echo "Downloading ledger..."
curl -sL "$LEDGER_URL" | gunzip > artifacts/ledger.wasm
curl -sL "$LEDGER_DID" > artifacts/ledger.did

echo "Downloading indexer..."
curl -sL "$INDEXER_URL" | gunzip > artifacts/indexer.wasm
curl -sL "$INDEXER_DID" > artifacts/indexer.did

echo "✅ Artifacts downloaded"
ls -la artifacts/
