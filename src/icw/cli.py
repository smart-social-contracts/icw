#!/usr/bin/env python3
"""ICW - ICP Wallet CLI for ICRC-1 tokens (ckBTC, ckETH, ICP)."""

import argparse

from icw import __version__
import json
import platform
import shutil
import subprocess
import sys
import urllib.request

TOKENS = {
    "ckbtc": ("mxzaz-hqaaa-aaaar-qaada-cai", "ckBTC", 8, 10, "bitcoin"),
    "cketh": ("ss2fx-dyaaa-aaaar-qacoq-cai", "ckETH", 18, 2000000000000, "ethereum"),
    "icp": ("ryjl3-tyaaa-aaaaa-aaaba-cai", "ICP", 8, 10000, "internet-computer"),
    "ckusdc": ("xevnm-gaaaa-aaaar-qafnq-cai", "ckUSDC", 6, 10000, "usd-coin"),
    "ckusdt": ("cngnf-vqaaa-aaaar-qag4q-cai", "ckUSDT", 6, 10000, "tether"),
    "realms": ("xbkkh-syaaa-aaaah-qq3ya-cai", "REALMS", 8, 10000, None),  # Custom token, no CoinGecko
}


def get_usd_price(coingecko_id):
    """Fetch USD price from CoinGecko (free, no API key)."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "ICW/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get(coingecko_id, {}).get("usd")
    except Exception:
        return None


_price_cache = {"data": {}, "timestamp": 0}


def get_all_prices():
    """Fetch all token prices in a single API call (cached for 30 seconds)."""
    import time

    now = time.time()
    # Return cached data if less than 30 seconds old
    if _price_cache["data"] and (now - _price_cache["timestamp"]) < 30:
        return _price_cache["data"]

    try:
        ids = ",".join(t[4] for t in TOKENS.values())  # coingecko IDs
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "ICW/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            result = {cg_id: data.get(cg_id, {}).get("usd") for cg_id in data}
            _price_cache["data"] = result
            _price_cache["timestamp"] = now
            return result
    except Exception:
        # Return stale cache if available
        return _price_cache["data"] or {}


def output(data):
    """Print JSON output (human-readable + machine-parseable)."""
    print(json.dumps(data, indent=2))


def detect_local_canisters():
    """Auto-detect canister IDs from dfx.json or canister_ids.json in current directory."""
    from pathlib import Path

    canisters = {}
    cwd = Path.cwd()

    # Map of common canister names to token keys
    name_map = {
        "ckbtc_ledger": "ckbtc",
        "ckbtc-ledger": "ckbtc",
        "ckbtc": "ckbtc",
        "cketh_ledger": "cketh",
        "cketh-ledger": "cketh",
        "cketh": "cketh",
        "icp_ledger": "icp",
        "icp-ledger": "icp",
        "ledger": "icp",
        "ckusdc_ledger": "ckusdc",
        "ckusdc-ledger": "ckusdc",
        "ckusdc": "ckusdc",
        "ckusdt_ledger": "ckusdt",
        "ckusdt-ledger": "ckusdt",
        "ckusdt": "ckusdt",
        "realms_ledger": "realms",
        "realms-ledger": "realms",
        "realms": "realms",
        "token_backend": "realms",
    }

    # Try canister_ids.json first (for local network)
    for filename in ["canister_ids.json", ".dfx/local/canister_ids.json"]:
        path = cwd / filename
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for name, info in data.items():
                    token = name_map.get(name.lower())
                    if token:
                        # Handle both {"canister_id": ...} and {"local": "..."}
                        if isinstance(info, dict):
                            cid = info.get("local") or info.get("ic") or info.get("canister_id")
                            if cid:
                                canisters[token] = cid
                        elif isinstance(info, str):
                            canisters[token] = info
            except Exception:
                # Ignore errors reading/parsing canister_ids.json; file may be malformed
                pass

    # Try dfx.json for canister definitions
    dfx_path = cwd / "dfx.json"
    if dfx_path.exists():
        try:
            data = json.loads(dfx_path.read_text())
            for name in data.get("canisters", {}):
                token = name_map.get(name.lower())
                if token and token not in canisters:
                    # dfx.json doesn't have IDs, but we note the canister exists
                    pass
        except Exception:
            # Ignore errors reading/parsing dfx.json; canister detection is best-effort
            pass

    return canisters


def ensure_dfx():
    """Check dfx is installed, offer to install if not."""
    if shutil.which("dfx"):
        return
    print("dfx not found. Install now? [y/N] ", end="")
    if input().strip().lower() not in ("y", "yes"):
        sys.exit('Install dfx: sh -ci "$(curl -fsSL https://internetcomputer.org/install.sh)"')
    if platform.system().lower() == "windows":
        sys.exit(
            "Use WSL on Windows. See: https://internetcomputer.org/docs/current/developer-docs/getting-started/install"
        )
    subprocess.run('sh -ci "$(curl -fsSL https://internetcomputer.org/install.sh)"', shell=True, check=True)
    if not shutil.which("dfx"):
        sys.exit("Install failed. Add ~/.local/share/dfx/bin to PATH")


# Candid field hash to name mappings (for when .did file is not available)
CANDID_HASH_MAP = {
    # MintResult fields
    "3_092_129_219": "success",
    "624_086_880": "block_index",
    "2_825_987_837": "new_balance",
    "1_932_118_984": "error",
}


def normalize_candid_response(obj):
    """Recursively replace Candid hash keys with field names."""
    if isinstance(obj, dict):
        return {CANDID_HASH_MAP.get(k, k): normalize_candid_response(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [normalize_candid_response(v) for v in obj]
    return obj


def dfx(args, network="ic"):
    """Run dfx command, return parsed JSON."""
    ensure_dfx()
    r = subprocess.run(["dfx"] + args + ["--network", network, "--output", "json"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Error: {r.stderr.strip()}")
    try:
        result = json.loads(r.stdout)
        return normalize_candid_response(result)
    except json.JSONDecodeError:
        return r.stdout.strip().replace("_", "").replace('"', "")


def principal():
    return subprocess.run(
        ["dfx", "identity", "get-principal"], capture_output=True, text=True, check=True
    ).stdout.strip()


def get_current_identity():
    """Get the name of the currently active dfx identity."""
    return subprocess.run(["dfx", "identity", "whoami"], capture_output=True, text=True, check=True).stdout.strip()


class use_identity:
    """Context manager to temporarily switch dfx identity."""

    def __init__(self, identity_name):
        self.identity_name = identity_name
        self.original_identity = None

    def __enter__(self):
        if self.identity_name:
            self.original_identity = get_current_identity()
            if self.original_identity != self.identity_name:
                subprocess.run(["dfx", "identity", "use", self.identity_name], capture_output=True, check=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_identity and self.original_identity != self.identity_name:
            subprocess.run(["dfx", "identity", "use", self.original_identity], capture_output=True, check=True)
        return False


def cmd_id(args):
    """Identity management."""
    ensure_dfx()
    if args.action == "list":
        current = subprocess.run(
            ["dfx", "identity", "whoami"], capture_output=True, text=True, check=True
        ).stdout.strip()
        r = subprocess.run(["dfx", "identity", "list"], capture_output=True, text=True, check=True)
        ids = [
            {"name": line.strip(), "active": line.strip() == current}
            for line in r.stdout.strip().split("\n")
            if line.strip()
        ]
        output({"identities": ids, "current": current})
    elif args.action == "use":
        subprocess.run(["dfx", "identity", "use", args.name], check=True)
        output({"switched": args.name, "principal": principal()})
    elif args.action == "new":
        subprocess.run(["dfx", "identity", "new", args.name], check=True)
        output({"created": args.name})
    elif args.action == "whoami":
        output(
            {
                "identity": subprocess.run(
                    ["dfx", "identity", "whoami"], capture_output=True, text=True, check=True
                ).stdout.strip(),
                "principal": principal(),
            }
        )


def subaccount(s):
    """Convert subaccount input to Candid blob format.

    Accepts:
    - Integer (0-255): last byte of 32-byte blob
    - Hex string (64 chars): direct 32-byte blob
    - Arbitrary text: ASCII bytes, right-padded to 32 bytes
    """
    if s is None or s == "" or s == "0" or s == 0:
        return "null"

    # Try as integer first
    try:
        n = int(s)
        if 0 <= n <= 255:
            blob = "\\00" * 31 + "\\{:02x}".format(n)
            return f'opt blob "{blob}"'
    except (ValueError, TypeError):
        pass

    s = str(s)

    # 64-char hex string → direct 32 bytes
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        blob = "".join(f"\\{s[i:i+2]}" for i in range(0, 64, 2))
        return f'opt blob "{blob}"'

    # Arbitrary text → ASCII bytes, padded to 32 bytes
    raw = s.encode("ascii")
    if len(raw) > 32:
        raise ValueError(f"Subaccount text too long: {len(raw)} bytes (max 32)")
    padded = raw.ljust(32, b"\x00")
    blob = "".join(f"\\{b:02x}" for b in padded)
    return f'opt blob "{blob}"'


def memo(s):
    """Convert memo input to Candid blob format.

    Accepts:
    - None/empty: returns null
    - Hex string (even length): direct bytes
    - Arbitrary text: ASCII bytes (max 32 bytes)
    """
    if s is None or s == "":
        return "null"

    s = str(s)

    # Hex string (non-empty, even length, all hex chars) → direct bytes
    if len(s) > 0 and len(s) % 2 == 0 and len(s) <= 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        blob = "".join(f"\\{s[i:i+2]}" for i in range(0, len(s), 2))
        return f'opt blob "{blob}"'

    # Arbitrary text → ASCII bytes
    raw = s.encode("ascii")
    if len(raw) > 32:
        raise ValueError(f"Memo too long: {len(raw)} bytes (max 32)")
    blob = "".join(f"\\{b:02x}" for b in raw)
    return f'opt blob "{blob}"'


def cmd_balance(args):
    ledger, name, dec, _, cg_id = TOKENS[args.token]
    # Auto-detect local ledgers if on local network
    if args.network == "local" and not args.ledger:
        local_ledgers = detect_local_canisters()
        ledger = local_ledgers.get(args.token) or ledger
    else:
        ledger = args.ledger or ledger  # allow override for testing

    identity = getattr(args, "identity", None)
    with use_identity(identity):
        p = args.principal or principal()
        bal = int(
            dfx(
                [
                    "canister",
                    "call",
                    ledger,
                    "icrc1_balance_of",
                    f'(record {{ owner = principal "{p}"; subaccount = {subaccount(args.subaccount)}; }})',
                ],
                args.network,
            )
            or 0
        )
    human = bal / 10**dec
    price = get_usd_price(cg_id)
    usd = round(human * price, 2) if price else None
    output({"token": name, "balance": human, "raw": bal, "usd": usd, "price": price, "principal": p})


def cmd_transfer(args):
    ledger, name, dec, fee, cg_id = TOKENS[args.token]
    # Auto-detect local ledgers if on local network
    if args.network == "local" and not args.ledger:
        local_ledgers = detect_local_canisters()
        ledger = local_ledgers.get(args.token) or ledger
    else:
        ledger = args.ledger or ledger  # allow override for testing
    fee = args.fee if args.fee is not None else fee  # allow override for testing
    amt = int(float(args.amount) * 10**dec) if "." in args.amount else int(args.amount)
    memo_val = memo(args.memo) if hasattr(args, "memo") else "null"

    identity = getattr(args, "identity", None)
    with use_identity(identity):
        r = dfx(
            [
                "canister",
                "call",
                ledger,
                "icrc1_transfer",
                f'(record {{ to = record {{ owner = principal "{args.recipient}"; subaccount = {subaccount(args.subaccount)}; }}; amount = {amt}; fee = opt {fee}; memo = {memo_val}; created_at_time = null; from_subaccount = {subaccount(args.from_subaccount)}; }})',
            ],
            args.network,
        )
    result = (
        {"ok": True, "block": r["Ok"], "token": name, "amount": amt / 10**dec, "to": args.recipient}
        if isinstance(r, dict) and "Ok" in r
        else None
    )
    if result and args.memo:
        result["memo"] = args.memo
    if result:
        output(result)
    elif isinstance(r, dict) and "Err" in r:
        output({"ok": False, "error": r["Err"]})
    else:
        output({"result": r})


def cmd_info(args):
    ledger, name, dec, fee, cg_id = TOKENS[args.token]
    price = get_usd_price(cg_id)
    output(
        {
            "token": name,
            "ledger": ledger,
            "decimals": dec,
            "fee": fee,
            "fee_human": fee / 10**dec,
            "price_usd": price,
            "principal": principal(),
            "network": args.network,
        }
    )


def cmd_mint(args):
    """Mint tokens (NON-STANDARD: requires canister with 'mint' method)."""
    ledger, name, dec, _, _ = TOKENS[args.token]
    # Auto-detect local ledgers if on local network
    if args.network == "local" and not args.ledger:
        local_ledgers = detect_local_canisters()
        ledger = local_ledgers.get(args.token) or ledger
    else:
        ledger = args.ledger or ledger

    p = args.recipient or principal()
    amt = int(float(args.amount) * 10**dec) if "." in args.amount else int(args.amount)

    r = dfx(
        [
            "canister",
            "call",
            ledger,
            "mint",
            f'(record {{ to = record {{ owner = principal "{p}"; subaccount = {subaccount(args.subaccount)}; }}; amount = {amt} : nat }})',
        ],
        args.network,
    )

    if isinstance(r, dict):
        if r.get("success"):
            output(
                {
                    "ok": True,
                    "block": r.get("block_index"),
                    "token": name,
                    "amount": amt / 10**dec,
                    "to": p,
                    "new_balance": r.get("new_balance"),
                }
            )
        elif r.get("error"):
            output({"ok": False, "error": r["error"]})
        else:
            output({"result": r})
    else:
        output({"result": r})


def cmd_ui(args):
    """Launch the web UI."""
    try:
        from icw.api import run_server
    except ImportError:
        sys.exit("UI dependencies not installed. Run: pip install internet-computer-wallet[ui]")

    # Build ledger config from args and auto-detection
    ledgers = detect_local_canisters() if args.network == "local" else {}

    # Override with explicit flags
    if hasattr(args, "ckbtc_ledger") and args.ckbtc_ledger:
        ledgers["ckbtc"] = args.ckbtc_ledger
    if hasattr(args, "cketh_ledger") and args.cketh_ledger:
        ledgers["cketh"] = args.cketh_ledger
    if hasattr(args, "icp_ledger") and args.icp_ledger:
        ledgers["icp"] = args.icp_ledger
    if hasattr(args, "ckusdc_ledger") and args.ckusdc_ledger:
        ledgers["ckusdc"] = args.ckusdc_ledger
    if hasattr(args, "ckusdt_ledger") and args.ckusdt_ledger:
        ledgers["ckusdt"] = args.ckusdt_ledger

    if ledgers:
        print(f"Auto-detected ledgers: {json.dumps(ledgers, indent=2)}")

    run_server(
        port=args.port,
        open_browser=not args.no_browser,
        network=args.network,
        ledgers=ledgers,
    )


def cmd_install_launcher(args):
    """Install desktop launcher (Linux only)."""
    import os
    import shutil as sh
    from pathlib import Path

    if platform.system() != "Linux":
        sys.exit("Desktop launcher is only supported on Linux")

    home = os.path.expanduser("~")
    apps_dir = os.path.join(home, ".local", "share", "applications")
    icons_dir = os.path.join(home, ".local", "share", "icons", "hicolor", "256x256", "apps")

    os.makedirs(apps_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)

    # Copy logo from package
    logo_src = Path(__file__).parent / "static" / "logo.png"
    icon_path = os.path.join(icons_dir, "icw.png")
    if logo_src.exists():
        sh.copy(logo_src, icon_path)
    else:
        # Fallback: create simple icon if logo not found
        icon_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="48" fill="#1a1a2e" stroke="#3b82f6" stroke-width="2"/>
  <text x="50" y="60" font-size="32" fill="white" text-anchor="middle" font-family="sans-serif" font-weight="bold">ICW</text>
</svg>"""
        with open(icon_path, "w") as f:
            f.write(icon_svg)

    # Create .desktop file (use full path to icon for PNG)
    desktop_entry = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=ICW Wallet
Comment=ICP Wallet for ICRC-1 tokens (ckBTC, ckETH, ICP, ckUSDC, ckUSDT)
Exec=icw ui
Icon={icon_path}
Categories=Finance;Utility;
Terminal=false
StartupNotify=true
Keywords=crypto;wallet;bitcoin;ethereum;icp;
"""

    desktop_path = os.path.join(apps_dir, "icw.desktop")
    with open(desktop_path, "w") as f:
        f.write(desktop_entry)

    # Update desktop database
    subprocess.run(["update-desktop-database", apps_dir], capture_output=True)

    output({"installed": True, "desktop_file": desktop_path, "icon": icon_path})
    print('\n✓ Launcher installed! Search for "ICW Wallet" in your applications menu.')


def main():
    p = argparse.ArgumentParser(prog="icw", description="ICP Wallet CLI")
    p.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--network", "-n", default="ic")
    p.add_argument("--token", "-t", default="ckbtc", choices=TOKENS.keys())
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("balance", aliases=["b"])
    b.add_argument("--principal", "-p")
    b.add_argument("--subaccount", "-s", default="0")
    b.add_argument("--ledger", "-l", help="Override ledger canister ID")
    b.add_argument("--identity", "-i", help="dfx identity to use (temporarily switches)")

    t = sub.add_parser("transfer", aliases=["t"])
    t.add_argument("recipient")
    t.add_argument("amount")
    t.add_argument("--subaccount", "-s", default="0")
    t.add_argument("--from-subaccount", "-f", default="0")
    t.add_argument("--ledger", "-l", help="Override ledger canister ID")
    t.add_argument("--fee", type=int, help="Override transfer fee")
    t.add_argument("--memo", "-m", help="Transaction memo/tag (max 32 bytes)")
    t.add_argument("--identity", "-i", help="dfx identity to use (temporarily switches)")

    m = sub.add_parser("mint", aliases=["m"], help="Mint tokens (NON-STANDARD)")
    m.add_argument("amount")
    m.add_argument("--recipient", "-r", help="Recipient principal (default: self)")
    m.add_argument("--subaccount", "-s", default="0")
    m.add_argument("--ledger", "-l", help="Override ledger canister ID")

    sub.add_parser("info", aliases=["i"])

    i = sub.add_parser("id", help="Identity management")
    i.add_argument("action", choices=["list", "use", "new", "whoami"], nargs="?", default="whoami")
    i.add_argument("name", nargs="?", help="Identity name (for use/new)")

    u = sub.add_parser("ui", help="Launch web UI")
    u.add_argument("--port", "-p", type=int, default=5555, help="Port to run on")
    u.add_argument("--no-browser", action="store_true", help="Don't open browser")
    u.add_argument("--network", "-n", default="ic", help="Network (ic or local)")
    u.add_argument("--ckbtc-ledger", help="ckBTC ledger canister ID (for local)")
    u.add_argument("--cketh-ledger", help="ckETH ledger canister ID (for local)")
    u.add_argument("--icp-ledger", help="ICP ledger canister ID (for local)")
    u.add_argument("--ckusdc-ledger", help="ckUSDC ledger canister ID (for local)")
    u.add_argument("--ckusdt-ledger", help="ckUSDT ledger canister ID (for local)")

    sub.add_parser("install-launcher", help="Install desktop launcher (Linux)")

    args = p.parse_args()
    {
        "balance": cmd_balance,
        "b": cmd_balance,
        "transfer": cmd_transfer,
        "t": cmd_transfer,
        "mint": cmd_mint,
        "m": cmd_mint,
        "info": cmd_info,
        "i": cmd_info,
        "id": cmd_id,
        "ui": cmd_ui,
        "install-launcher": cmd_install_launcher,
    }[args.cmd](args)


def ui():
    """Launch the web UI."""
    try:
        from icw.api import run_server
    except ImportError:
        sys.exit("UI dependencies not installed. Run: pip install internet-computer-wallet[ui]")
    run_server()


if __name__ == "__main__":
    main()
