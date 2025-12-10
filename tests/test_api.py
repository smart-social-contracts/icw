#!/usr/bin/env python3
"""Tests for ICW Web API - no browser required."""
import sys

sys.path.insert(0, "src")

from fastapi.testclient import TestClient
from icw.api import app


client = TestClient(app)


def test_index_returns_html():
    """Home page should return HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ICW" in response.text
    print("✓ test_index_returns_html")


def test_api_identity():
    """Identity endpoint should return current identity."""
    response = client.get("/api/identity")
    # May return 500 if dfx identity not set up in CI
    if response.status_code == 500:
        print("⚠ test_api_identity (skipped - dfx not configured)")
        return
    assert response.status_code == 200
    data = response.json()
    assert "identity" in data
    assert "principal" in data
    print("✓ test_api_identity")


def test_api_identities():
    """Identities endpoint should list all identities."""
    response = client.get("/api/identities")
    # May return 500 if dfx identity not set up in CI
    if response.status_code == 500:
        print("⚠ test_api_identities (skipped - dfx not configured)")
        return
    assert response.status_code == 200
    data = response.json()
    assert "identities" in data
    assert "current" in data
    assert isinstance(data["identities"], list)
    print("✓ test_api_identities")


def test_api_balance_invalid_token():
    """Balance with invalid token should return 400."""
    response = client.get("/api/balance/invalid_token")
    assert response.status_code == 400
    print("✓ test_api_balance_invalid_token")


def test_api_info():
    """Info endpoint should return token details."""
    response = client.get("/api/info/ckbtc")
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == "ckBTC"
    assert data["decimals"] == 8
    assert "ledger" in data
    print("✓ test_api_info")


def test_api_info_all_tokens():
    """Info endpoint should work for all supported tokens."""
    for token in ["ckbtc", "cketh", "icp"]:
        response = client.get(f"/api/info/{token}")
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "decimals" in data
        assert "fee" in data
    print("✓ test_api_info_all_tokens")


def test_api_transfer_missing_fields():
    """Transfer without required fields should fail validation."""
    response = client.post("/api/transfer", json={})
    assert response.status_code == 422  # Validation error
    print("✓ test_api_transfer_missing_fields")


def test_api_transfer_invalid_token():
    """Transfer with invalid token should return 400."""
    response = client.post(
        "/api/transfer",
        json={
            "token": "invalid",
            "recipient": "aaaaa-aa",
            "amount": "1.0",
        },
    )
    assert response.status_code == 400
    print("✓ test_api_transfer_invalid_token")


def test_api_prices():
    """Prices endpoint should return token prices."""
    response = client.get("/api/prices")
    assert response.status_code == 200
    data = response.json()
    assert "prices" in data
    assert "timestamp" in data
    # Check all tokens are present
    for token in ["ckbtc", "cketh", "icp", "ckusdc", "ckusdt"]:
        assert token in data["prices"]
        assert "name" in data["prices"][token]
        assert "coingecko_id" in data["prices"][token]
    print("✓ test_api_prices")


def test_api_config():
    """Config endpoint should return server configuration."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "network" in data
    assert "ledgers" in data
    assert isinstance(data["ledgers"], dict)
    print("✓ test_api_config")


def test_api_logo():
    """Logo endpoint should return image."""
    response = client.get("/logo.png")
    assert response.status_code == 200
    assert "image/png" in response.headers["content-type"]
    print("✓ test_api_logo")


if __name__ == "__main__":
    test_index_returns_html()
    test_api_identity()
    test_api_identities()
    test_api_balance_invalid_token()
    test_api_info()
    test_api_info_all_tokens()
    test_api_transfer_missing_fields()
    test_api_transfer_invalid_token()
    test_api_prices()
    test_api_config()
    test_api_logo()
    print("\nAll API tests passed!")
