#!/usr/bin/env python3
"""Integration tests with local ckBTC ledger canister."""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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


def icw(*args):
    """Run icw CLI from tests directory (where dfx.json is)."""
    result = subprocess.run(
        [sys.executable, "-m", "icw.cli"] + list(args),
        capture_output=True,
        text=True,
        cwd=TEST_DIR,  # must be where dfx.json is
        env={**os.environ, "PYTHONPATH": os.path.join(TEST_DIR, "..", "src")},
    )
    return result


def test_balance():
    """Test icw balance command."""
    print("\n=== Test: icw balance ===")
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])

    result = icw("-n", "local", "balance", "-l", local_ledger)
    print(f"icw balance: {result.stdout}")
    if result.returncode != 0:
        print(f"stderr: {result.stderr}")
    assert result.returncode == 0, f"icw balance failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data["balance"] == 1000.0, f"Expected 1000.0, got {data['balance']}"
    assert data["raw"] == 100_000_000_000
    print(f"✓ Balance correct: {data['balance']} ckBTC")


def test_transfer():
    """Test icw transfer command."""
    print("\n=== Test: icw transfer ===")
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])
    principal = get_principal()

    result = icw("-n", "local", "transfer", principal, "0.01", "-s", "1", "-l", local_ledger, "--fee", "0")
    print(f"icw transfer: {result.stdout}")
    if result.returncode != 0:
        print(f"stderr: {result.stderr}")
    assert result.returncode == 0, f"icw transfer failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data.get("ok") or "block" in str(data), f"Transfer failed: {data}"
    print("✓ Transfer successful")


def test_transfer_with_balance_verification():
    """Test transfer by verifying sender and receiver balances."""
    print("\n=== Test: transfer with balance verification ===")
    local_ledger = run(["dfx", "canister", "id", "ckbtc_ledger"])
    principal = get_principal()

    # First, fund subaccount 1 from minting account (default) so we have a non-minting sender
    print("Funding subaccount 1 from minting account...")
    result = icw("-n", "local", "transfer", principal, "0.1", "-s", "1", "-l", local_ledger, "--fee", "0")
    assert result.returncode == 0, f"Failed to fund subaccount 1: {result.stderr}"

    # Get sender's initial balance (subaccount 1 - NOT the minting account)
    result = icw("-n", "local", "balance", "-s", "1", "-l", local_ledger)
    assert result.returncode == 0, f"Failed to get sender balance: {result.stderr}"
    sender_before = json.loads(result.stdout)
    sender_balance_before = sender_before["raw"]
    print(f"Sender (subaccount 1) balance before: {sender_before['balance']} ckBTC (raw: {sender_balance_before})")

    # Get receiver's initial balance (subaccount 2)
    result = icw("-n", "local", "balance", "-s", "2", "-l", local_ledger)
    assert result.returncode == 0, f"Failed to get receiver balance: {result.stderr}"
    receiver_before = json.loads(result.stdout)
    receiver_balance_before = receiver_before["raw"]
    print(
        f"Receiver (subaccount 2) balance before: {receiver_before['balance']} ckBTC (raw: {receiver_balance_before})"
    )

    # Transfer amount (in raw units: 0.01 ckBTC = 1,000,000 satoshis)
    transfer_amount_btc = 0.01
    transfer_amount_raw = 1_000_000
    fee_raw = 10  # non-minting account transfers require actual fee

    # Perform transfer from subaccount 1 to subaccount 2
    result = icw(
        "-n",
        "local",
        "transfer",
        principal,
        str(transfer_amount_btc),
        "-s",
        "2",
        "-f",
        "1",
        "-l",
        local_ledger,
        "--fee",
        "10",
    )
    print(f"Transfer result: {result.stdout}")
    assert result.returncode == 0, f"Transfer failed: {result.stderr}"

    transfer_data = json.loads(result.stdout)
    assert transfer_data.get("ok"), f"Transfer not successful: {transfer_data}"
    print(f"✓ Transfer executed (block: {transfer_data.get('block')})")

    # Get sender's balance after transfer (subaccount 1)
    result = icw("-n", "local", "balance", "-s", "1", "-l", local_ledger)
    assert result.returncode == 0, f"Failed to get sender balance after: {result.stderr}"
    sender_after = json.loads(result.stdout)
    sender_balance_after = sender_after["raw"]
    print(f"Sender (subaccount 1) balance after: {sender_after['balance']} ckBTC (raw: {sender_balance_after})")

    # Get receiver's balance after transfer (subaccount 2)
    result = icw("-n", "local", "balance", "-s", "2", "-l", local_ledger)
    assert result.returncode == 0, f"Failed to get receiver balance after: {result.stderr}"
    receiver_after = json.loads(result.stdout)
    receiver_balance_after = receiver_after["raw"]
    print(f"Receiver (subaccount 2) balance after: {receiver_after['balance']} ckBTC (raw: {receiver_balance_after})")

    # Verify sender's balance decreased by transfer amount + fee
    expected_sender_decrease = transfer_amount_raw + fee_raw
    actual_sender_decrease = sender_balance_before - sender_balance_after
    assert (
        actual_sender_decrease == expected_sender_decrease
    ), f"Sender balance decreased by {actual_sender_decrease}, expected {expected_sender_decrease}"
    print(f"✓ Sender balance decreased correctly by {actual_sender_decrease} (amount + fee)")

    # Verify receiver's balance increased by transfer amount (no fee deducted from receiver)
    expected_receiver_increase = transfer_amount_raw
    actual_receiver_increase = receiver_balance_after - receiver_balance_before
    assert (
        actual_receiver_increase == expected_receiver_increase
    ), f"Receiver balance increased by {actual_receiver_increase}, expected {expected_receiver_increase}"
    print(f"✓ Receiver balance increased correctly by {actual_receiver_increase}")

    print("✓ Transfer verified: balances match expected values")


def test_icw_id():
    """Test icw id command."""
    print("\n=== Test: icw id ===")

    result = icw("id")
    print(f"icw id: {result.stdout}")
    assert result.returncode == 0, f"icw id failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert "identity" in data
    assert "principal" in data
    print("✓ icw id works")


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
    test_icw_id()
    test_balance()
    test_transfer()
    test_transfer_with_balance_verification()

    print("\n" + "=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
