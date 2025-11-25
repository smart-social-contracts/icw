#!/usr/bin/env python3
"""Tests for ICW CLI - plain Python, no frameworks."""
import sys

sys.path.insert(0, "src")

from icw.cli import TOKENS, subaccount


def test_tokens():
    assert "ckbtc" in TOKENS, "ckbtc should be in TOKENS"
    assert "cketh" in TOKENS, "cketh should be in TOKENS"
    assert "icp" in TOKENS, "icp should be in TOKENS"
    assert TOKENS["ckbtc"][0] == "mxzaz-hqaaa-aaaar-qaada-cai"
    assert TOKENS["ckbtc"][2] == 8  # decimals
    print("✓ test_tokens")


def test_subaccount():
    assert subaccount(0) == "null"
    assert "opt blob" in subaccount(1)
    assert "\\01" in subaccount(1)
    assert "\\ff" in subaccount(255)
    print("✓ test_subaccount")


def test_token_structure():
    for name, (ledger, symbol, decimals, fee, cg_id) in TOKENS.items():
        assert ledger.endswith("-cai"), f"{name} ledger should end with -cai"
        assert decimals > 0, f"{name} should have positive decimals"
        assert fee >= 0, f"{name} should have non-negative fee"
        assert cg_id, f"{name} should have coingecko id"
    print("✓ test_token_structure")


if __name__ == "__main__":
    test_tokens()
    test_subaccount()
    test_token_structure()
    print("\nAll tests passed!")
