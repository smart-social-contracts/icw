#!/bin/bash
# Download ICRC ledger and indexer wasm files
set -e
cd "$(dirname "$0")"
mkdir -p artifacts

# Use stable IC release
IC_VERSION="2e269c77a55006def0cc02fb0dd19834ae71994d"
BASE_URL="https://download.dfinity.systems/ic/${IC_VERSION}/canisters"

echo "Downloading ledger wasm..."
curl -sLf "${BASE_URL}/ic-icrc1-ledger.wasm.gz" | gunzip > artifacts/ledger.wasm

echo "Downloading indexer wasm..."
curl -sLf "${BASE_URL}/ic-icrc1-index-ng.wasm.gz" | gunzip > artifacts/indexer.wasm

# Create minimal .did files (dfx only needs basic structure)
cat > artifacts/ledger.did << 'EOF'
service : {}
EOF

cat > artifacts/indexer.did << 'EOF'
service : {}
EOF

echo "✅ Artifacts downloaded"
ls -la artifacts/
