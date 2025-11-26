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
    r = dfx(
        [
            "canister",
            "call",
            ledger,
            "icrc1_transfer",
            f'(record {{ to = record {{ owner = principal "{args.recipient}"; subaccount = {subaccount(args.subaccount)}; }}; amount = {amt}; fee = opt {fee}; memo = null; created_at_time = null; from_subaccount = {subaccount(args.from_subaccount)}; }})',
        ],
        args.network,
    )
    if isinstance(r, dict) and "Ok" in r:
        output({"ok": True, "block": r["Ok"], "token": name, "amount": amt / 10**dec, "to": args.recipient})
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

    sub.add_parser("info", aliases=["i"])

    i = sub.add_parser("id", help="Identity management")
    i.add_argument("action", choices=["list", "use", "new", "whoami"], nargs="?", default="whoami")
    i.add_argument("name", nargs="?", help="Identity name (for use/new)")

    args = p.parse_args()
    {
        "balance": cmd_balance,
        "b": cmd_balance,
        "transfer": cmd_transfer,
        "t": cmd_transfer,
        "info": cmd_info,
        "i": cmd_info,
        "id": cmd_id,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
