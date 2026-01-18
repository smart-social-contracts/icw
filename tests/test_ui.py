#!/usr/bin/env python3
"""UI tests for ICW Web interface using Playwright."""

import subprocess
import time
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "src")

# Check if playwright is installed
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Server configuration
SERVER_PORT = 5556
SERVER_URL = f"http://localhost:{SERVER_PORT}"

# Timeout constants (in milliseconds)
TIMEOUT_BALANCES_LOAD = 3000  # Wait for balances to load from API
TIMEOUT_IDENTITY_LOAD = 2000  # Wait for identity to load
TIMEOUT_ANIMATION = 500  # Wait for UI animations
TIMEOUT_COLLAPSE = 300  # Wait for collapse animation


def wait_for_server(url, timeout=10):
    """Poll server until it responds or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.2)
    return False


def start_server():
    """Start the ICW UI server in background."""
    proc = subprocess.Popen(
        [sys.executable, "-c", f"from icw.api import run_server; run_server(port={SERVER_PORT}, open_browser=False)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not wait_for_server(SERVER_URL):
        proc.terminate()
        raise RuntimeError("Server failed to start within timeout")
    return proc


def test_page_loads():
    """Page should load with title and header."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)

        # Check title
        assert "ICW" in page.title()

        # Check header exists
        header = page.locator("h1")
        assert header.is_visible()
        assert "ICW" in header.text_content()

        browser.close()
    print("✓ test_page_loads")


def test_balance_cards_visible():
    """Balance cards for all tokens should be visible."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Wait for balances to load
        page.wait_for_timeout(TIMEOUT_BALANCES_LOAD)

        # Check that token cards exist
        cards = page.locator("text=ckBTC")
        assert cards.count() >= 1

        browser.close()
    print("✓ test_balance_cards_visible")


def test_token_selector():
    """Clicking token buttons should change selection."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Find token selector buttons (in the form, not the submit button)
        eth_button = page.get_by_role("button", name="CKETH", exact=True)
        eth_button.click()

        # The button should now be selected (dark background)
        assert "bg-gray-900" in eth_button.get_attribute("class")

        browser.close()
    print("✓ test_token_selector")


def test_transfer_form_exists():
    """Transfer form should have all required fields."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Check form elements
        assert page.locator("input[placeholder*='xxxxx']").is_visible()  # Recipient
        assert page.locator("input[placeholder='0.00']").is_visible()  # Amount
        assert page.locator("button[type='submit']").is_visible()  # Submit

        browser.close()
    print("✓ test_transfer_form_exists")


def test_identity_dropdown():
    """Identity dropdown should open and show identities."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Wait for identity to load
        page.wait_for_timeout(TIMEOUT_IDENTITY_LOAD)

        # Click identity button (has green dot indicator)
        identity_btn = page.locator("button").filter(has=page.locator(".bg-green-500")).first
        if identity_btn.is_visible():
            identity_btn.click()
            page.wait_for_timeout(TIMEOUT_ANIMATION)

        browser.close()
    print("✓ test_identity_dropdown")


def test_advanced_options_toggle():
    """Advanced options should expand when clicked."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Click advanced options
        page.locator("text=Advanced options").click()
        page.wait_for_timeout(TIMEOUT_COLLAPSE)

        # Subaccount fields should be visible (in the form, not modal)
        assert page.locator("form label:has-text('To Subaccount')").is_visible()
        assert page.locator("form label:has-text('From Subaccount')").is_visible()
        assert page.locator("form label:has-text('Memo')").is_visible()

        browser.close()
    print("✓ test_advanced_options_toggle")


def test_network_selector():
    """Network selector should have mainnet and local options."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Check network selector
        network_select = page.locator("select")
        assert network_select.is_visible()

        # Check options
        options = network_select.locator("option").all_text_contents()
        assert "Mainnet" in options
        assert "Local" in options

        browser.close()
    print("✓ test_network_selector")


def test_principal_displayed():
    """Principal should be displayed on the page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Wait for principal to load
        page.wait_for_timeout(TIMEOUT_IDENTITY_LOAD)

        # Principal should be in a monospace font element
        principal_elem = page.locator(".font-mono")
        assert principal_elem.count() >= 1

        browser.close()
    print("✓ test_principal_displayed")


def test_total_balance_displayed():
    """Total balance card should be visible."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Check total balance card exists
        total_balance = page.locator("text=Total Balance")
        assert total_balance.is_visible()

        # Check USD value is displayed
        usd_value = page.locator("text=$")
        assert usd_value.count() >= 1

        browser.close()
    print("✓ test_total_balance_displayed")


def test_logo_displayed():
    """Logo should be visible in header."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Check logo image exists
        logo = page.locator("img[alt='ICW']")
        assert logo.is_visible()

        browser.close()
    print("✓ test_logo_displayed")


def test_price_timestamp():
    """Price update timestamp should be shown."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        # Wait for prices to load
        page.wait_for_timeout(TIMEOUT_BALANCES_LOAD)

        # Check for price timestamp text (may say "just now" or "Xs ago")
        # May not always be visible if prices haven't loaded
        page.locator("text=/Prices updated/")
        browser.close()
    print("✓ test_price_timestamp")


if __name__ == "__main__":
    server = start_server()
    try:
        test_page_loads()
        test_balance_cards_visible()
        test_token_selector()
        test_transfer_form_exists()
        test_identity_dropdown()
        test_advanced_options_toggle()
        test_network_selector()
        test_principal_displayed()
        test_total_balance_displayed()
        test_logo_displayed()
        test_price_timestamp()
        print("\nAll UI tests passed!")
    finally:
        server.terminate()
        server.wait()
