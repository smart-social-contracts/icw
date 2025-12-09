#!/usr/bin/env python3
"""Tests for ICW CLI - plain Python, no frameworks."""
import sys

sys.path.insert(0, "src")

from icw.cli import TOKENS, subaccount, memo


def test_tokens():
    assert "ckbtc" in TOKENS, "ckbtc should be in TOKENS"
    assert "cketh" in TOKENS, "cketh should be in TOKENS"
    assert "icp" in TOKENS, "icp should be in TOKENS"
    assert "ckusdc" in TOKENS, "ckusdc should be in TOKENS"
    assert "ckusdt" in TOKENS, "ckusdt should be in TOKENS"
    assert TOKENS["ckbtc"][0] == "mxzaz-hqaaa-aaaar-qaada-cai"
    assert TOKENS["ckbtc"][2] == 8  # decimals
    assert TOKENS["ckusdc"][2] == 6  # stablecoins have 6 decimals
    assert TOKENS["ckusdt"][2] == 6  # stablecoins have 6 decimals
    print("✓ test_tokens")


def test_subaccount():
    assert subaccount(0) == "null"
    assert "opt blob" in subaccount(1)
    assert "\\01" in subaccount(1)
    assert "\\ff" in subaccount(255)
    print("✓ test_subaccount")


def test_memo():
    # Empty/null cases
    assert memo(None) == "null"
    assert memo("") == "null"
    
    # Text memo (ASCII bytes)
    result = memo("invoice_123")
    assert "opt blob" in result
    assert "\\69" in result  # 'i' = 0x69
    assert "\\6e" in result  # 'n' = 0x6e
    
    # Hex string (even length, all hex chars) -> direct bytes
    hex_result = memo("0a1b2c3d")
    assert "opt blob" in hex_result
    assert "\\0a" in hex_result
    assert "\\1b" in hex_result
    
    # Short text
    short = memo("abc")
    assert "opt blob" in short
    assert "\\61" in short  # 'a' = 0x61
    
    # Test that memo too long raises error
    try:
        memo("a" * 33)  # 33 bytes, should fail
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "too long" in str(e)
    
    print("✓ test_memo")


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
    test_memo()
    test_token_structure()
    print("\nAll tests passed!")
