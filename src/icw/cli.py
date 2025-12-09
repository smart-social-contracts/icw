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
}


def get_usd_price(coingecko_id):
    """Fetch USD price from CoinGecko (free, no API key)."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read()).get(coingecko_id, {}).get("usd")
    except Exception:
        return None


def output(data):
    """Print JSON output (human-readable + machine-parseable)."""
    print(json.dumps(data, indent=2))


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


def dfx(args, network="ic"):
    """Run dfx command, return parsed JSON."""
    ensure_dfx()
    r = subprocess.run(["dfx"] + args + ["--network", network, "--output", "json"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Error: {r.stderr.strip()}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip().replace("_", "").replace('"', "")


def principal():
    return subprocess.run(
        ["dfx", "identity", "get-principal"], capture_output=True, text=True, check=True
    ).stdout.strip()


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

    # Hex string (even length, all hex chars) → direct bytes
    if len(s) % 2 == 0 and len(s) <= 64 and all(c in "0123456789abcdefABCDEF" for c in s):
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
    ledger = args.ledger or ledger  # allow override for testing
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
    ledger = args.ledger or ledger  # allow override for testing
    fee = args.fee if args.fee is not None else fee  # allow override for testing
    amt = int(float(args.amount) * 10**dec) if "." in args.amount else int(args.amount)
    memo_val = memo(args.memo) if hasattr(args, "memo") else "null"
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


def cmd_ui(args):
    """Launch the web UI."""
    try:
        from icw.api import run_server
    except ImportError:
        sys.exit("UI dependencies not installed. Run: pip install internet-computer-wallet[ui]")
    run_server(port=args.port, open_browser=not args.no_browser)


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

    t = sub.add_parser("transfer", aliases=["t"])
    t.add_argument("recipient")
    t.add_argument("amount")
    t.add_argument("--subaccount", "-s", default="0")
    t.add_argument("--from-subaccount", "-f", default="0")
    t.add_argument("--ledger", "-l", help="Override ledger canister ID")
    t.add_argument("--fee", type=int, help="Override transfer fee")
    t.add_argument("--memo", "-m", help="Transaction memo/tag (max 32 bytes)")

    sub.add_parser("info", aliases=["i"])

    i = sub.add_parser("id", help="Identity management")
    i.add_argument("action", choices=["list", "use", "new", "whoami"], nargs="?", default="whoami")
    i.add_argument("name", nargs="?", help="Identity name (for use/new)")

    u = sub.add_parser("ui", help="Launch web UI")
    u.add_argument("--port", "-p", type=int, default=5555, help="Port to run on")
    u.add_argument("--no-browser", action="store_true", help="Don't open browser")

    args = p.parse_args()
    {
        "balance": cmd_balance,
        "b": cmd_balance,
        "transfer": cmd_transfer,
        "t": cmd_transfer,
        "info": cmd_info,
        "i": cmd_info,
        "id": cmd_id,
        "ui": cmd_ui,
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
