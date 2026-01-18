#!/usr/bin/env python3
"""Tests for ICW CLI - plain Python, no frameworks."""

import sys

sys.path.insert(0, "src")

from icw.cli import TOKENS, subaccount, memo, normalize_candid_response, CANDID_HASH_MAP


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
        assert cg_id or name == "realms", f"{name} should have coingecko id"
    print("✓ test_token_structure")


def test_detect_local_canisters():
    """Test auto-detection of canister IDs from project files."""
    from icw.cli import detect_local_canisters
    import tempfile
    import os
    import json

    # Test with no files (should return empty dict)
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = detect_local_canisters()
        assert result == {}, f"Expected empty dict, got {result}"

        # Test with canister_ids.json
        canister_ids = {
            "ckbtc_ledger": {"local": "bkyz2-fmaaa-aaaaa-qaaaq-cai"},
            "icp_ledger": {"local": "ryjl3-tyaaa-aaaaa-aaaba-cai"},
        }
        with open("canister_ids.json", "w") as f:
            json.dump(canister_ids, f)

        result = detect_local_canisters()
        assert result.get("ckbtc") == "bkyz2-fmaaa-aaaaa-qaaaq-cai"
        assert result.get("icp") == "ryjl3-tyaaa-aaaaa-aaaba-cai"

        os.chdir(original_cwd)
    print("✓ test_detect_local_canisters")


def test_price_cache():
    """Test that price caching works correctly."""
    from icw.cli import get_all_prices, _price_cache
    import time

    # Clear cache
    _price_cache["data"] = {}
    _price_cache["timestamp"] = 0

    # First call should try to fetch (may fail due to rate limits, that's ok)
    get_all_prices()
    timestamp1 = _price_cache["timestamp"]

    # Second call within 30 seconds should return cached data
    time.sleep(0.1)
    get_all_prices()
    timestamp2 = _price_cache["timestamp"]

    # Timestamps should be the same (cache hit)
    assert timestamp1 == timestamp2, "Cache should be used for second call"
    print("✓ test_price_cache")


def test_mint_command_exists():
    """Test that mint command is registered in CLI."""
    from icw.cli import cmd_mint

    # Verify cmd_mint function exists and is callable
    assert callable(cmd_mint), "cmd_mint should be callable"

    # Verify mint is in the parser by checking help output
    import subprocess

    result = subprocess.run(["icw", "mint", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"mint --help should succeed: {result.stderr}"
    assert "amount" in result.stdout.lower(), "mint should have amount argument"
    assert "recipient" in result.stdout.lower(), "mint should have recipient option"
    assert "ledger" in result.stdout.lower(), "mint should have ledger option"
    print("✓ test_mint_command_exists")


def test_mint_command_args():
    """Test mint command argument parsing."""
    import subprocess

    # Test 'm' alias works
    result = subprocess.run(["icw", "m", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"mint alias 'm' should work: {result.stderr}"
    assert "NON-STANDARD" in result.stdout or "amount" in result.stdout.lower(), "should show mint help"
    print("✓ test_mint_command_args")


def test_normalize_candid_response():
    """Test that Candid hash keys are properly normalized to field names.

    This catches issues where dfx returns numeric hash keys instead of field names
    when the .did file is not available (e.g., calling a canister from icw without
    the local Candid interface).
    """
    # Test MintResult hash keys -> field names
    raw_response = {
        "3_092_129_219": True,
        "624_086_880": ["1"],
        "2_825_987_837": ["100_000_000"],
        "1_932_118_984": [],
    }
    normalized = normalize_candid_response(raw_response)

    assert "success" in normalized, f"Expected 'success' field, got {normalized.keys()}"
    assert "block_index" in normalized, f"Expected 'block_index' field, got {normalized.keys()}"
    assert "new_balance" in normalized, f"Expected 'new_balance' field, got {normalized.keys()}"
    assert "error" in normalized, f"Expected 'error' field, got {normalized.keys()}"

    assert normalized["success"] is True
    assert normalized["block_index"] == ["1"]
    assert normalized["new_balance"] == ["100_000_000"]
    assert normalized["error"] == []

    # Test nested structures
    nested = {"outer": {"3_092_129_219": True}}
    normalized_nested = normalize_candid_response(nested)
    assert normalized_nested["outer"]["success"] is True

    # Test lists with dicts
    list_response = [{"3_092_129_219": False}, {"624_086_880": ["2"]}]
    normalized_list = normalize_candid_response(list_response)
    assert normalized_list[0]["success"] is False
    assert normalized_list[1]["block_index"] == ["2"]

    # Test that unknown keys are preserved
    unknown = {"unknown_key": "value", "3_092_129_219": True}
    normalized_unknown = normalize_candid_response(unknown)
    assert normalized_unknown["unknown_key"] == "value"
    assert normalized_unknown["success"] is True

    # Test primitives pass through unchanged
    assert normalize_candid_response("string") == "string"
    assert normalize_candid_response(123) == 123
    assert normalize_candid_response(None) is None

    print("✓ test_normalize_candid_response")


def test_candid_hash_map_completeness():
    """Test that CANDID_HASH_MAP contains expected MintResult fields."""
    expected_fields = {"success", "block_index", "new_balance", "error"}
    actual_fields = set(CANDID_HASH_MAP.values())

    for field in expected_fields:
        assert field in actual_fields, f"Missing field '{field}' in CANDID_HASH_MAP"

    print("✓ test_candid_hash_map_completeness")


if __name__ == "__main__":
    test_tokens()
    test_subaccount()
    test_memo()
    test_token_structure()
    test_detect_local_canisters()
    test_price_cache()
    test_mint_command_exists()
    test_mint_command_args()
    test_normalize_candid_response()
    test_candid_hash_map_completeness()
    print("\nAll tests passed!")
