#!/usr/bin/env python3
"""Integration tests with local ckBTC ledger canister."""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from icw.cli import TOKENS

NETWORK = "local"
TEST_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)
    if check and r.returncode != 0:
        print(f"STDERR: {r.stderr}")
        raise RuntimeError(f"Command failed: {r.returncode}")
    return r.stdout.strip()


def get_principal():
    return run(["dfx", "identity", "get-principal"])


def deploy_ledger():
    """Deploy ckBTC ledger with initial balance to current principal."""
    principal = get_principal()
    print(f"Deploying ledger for principal: {principal}")

    init_arg = (
        "(variant { Init = record { "
        f'minting_account = record {{ owner = principal "{principal}"; subaccount = null }}; '
        "transfer_fee = 10; "
        'token_symbol = "ckBTC"; '
        'token_name = "ckBTC Test"; '
        "decimals = opt 8; "
        "metadata = vec {}; "
        f'initial_balances = vec {{ record {{ record {{ owner = principal "{principal}"; subaccount = null }}; 100_000_000_000 }} }}; '
        "feature_flags = opt record { icrc2 = true }; "
        f'archive_options = record {{ num_blocks_to_archive = 1000; trigger_threshold = 2000; controller_id = principal "{principal}" }} '
        "} })"
    )

    run(["dfx", "deploy", "ckbtc_ledger", "--no-wallet", "--yes", f"--argument={init_arg}"])
    return run(["dfx", "canister", "id", "ckbtc_ledger"])


def deploy_indexer(ledger_id):
    """Deploy ckBTC indexer."""
    init_arg = (
        f"(opt variant {{ Init = record {{ "
        f'ledger_id = principal "{ledger_id}"; '
        f"retrieve_blocks_from_ledger_interval_seconds = opt 1 "
        f"}} }})"
    )
    run(["dfx", "deploy", "ckbtc_indexer", "--no-wallet", f"--argument={init_arg}"])
    return run(["dfx", "canister", "id", "ckbtc_indexer"])


def test_balance():
    """Test balance query."""
    print("\n=== Test: Balance ===")
    ledger_id, _, dec, _, _ = TOKENS["ckbtc"]

    # Override ledger ID with local canister
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])
    principal = get_principal()

    result = run(
        [
            "dfx",
            "canister",
            "call",
            local_ledger,
            "icrc1_balance_of",
            f'(record {{ owner = principal "{principal}"; subaccount = null }})',
        ]
    )
    print(f"Balance result: {result}")

    # Parse result (format: "(1_000 : nat)")
    balance = int(result.replace("(", "").replace(")", "").replace("_", "").replace(": nat", "").strip())
    assert balance == 100_000_000_000, f"Expected 100_000_000_000, got {balance}"
    print(f"✓ Balance correct: {balance / 10**8} ckBTC")


def test_transfer():
    """Test transfer."""
    print("\n=== Test: Transfer ===")
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])
    principal = get_principal()

    # Transfer to self (subaccount 1)
    result = run(
        [
            "dfx",
            "canister",
            "call",
            local_ledger,
            "icrc1_transfer",
            f"""(record {{
                to = record {{ owner = principal "{principal}"; subaccount = opt blob "\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\00\\01" }};
                amount = 1_000_000;
                fee = opt 10;
                memo = null;
                created_at_time = null;
                from_subaccount = null
            }})""",
        ]
    )
    print(f"Transfer result: {result}")
    assert "Ok" in result, f"Transfer failed: {result}"
    print("✓ Transfer successful")


def test_icw_cli():
    """Test icw CLI against local ledger."""
    print("\n=== Test: ICW CLI ===")

    # Get local ledger ID
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])
    print(f"Local ledger: {local_ledger}")

    # Test icw id command
    result = subprocess.run(
        [sys.executable, "-m", "icw.cli", "id"],
        capture_output=True,
        text=True,
        cwd=os.path.join(TEST_DIR, ".."),
        env={**os.environ, "PYTHONPATH": os.path.join(TEST_DIR, "..", "src")},
    )
    print(f"icw id: {result.stdout}")
    assert result.returncode == 0, f"icw id failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert "identity" in data
    assert "principal" in data
    print("✓ ICW CLI works")


def main():
    print("=" * 60)
    print("ICW Integration Tests")
    print("=" * 60)

    # Check dfx is running
    try:
        run(["dfx", "ping"], check=False)
    except Exception:
        print("Starting dfx...")
        subprocess.Popen(["dfx", "start", "--clean", "--background"], cwd=TEST_DIR)
        time.sleep(5)

    # Deploy canisters
    print("\n=== Deploying Canisters ===")
    ledger_id = deploy_ledger()
    print(f"Ledger ID: {ledger_id}")

    indexer_id = deploy_indexer(ledger_id)
    print(f"Indexer ID: {indexer_id}")

    # Run tests
    test_balance()
    test_transfer()
    test_icw_cli()

    print("\n" + "=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
