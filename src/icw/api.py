#!/usr/bin/env python3
"""ICW Web API - FastAPI server for the wallet UI."""
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from icw.cli import (
    TOKENS,
    dfx,
    ensure_dfx,
    get_all_prices,
    get_usd_price,
    memo,
    principal,
    subaccount,
)

app = FastAPI(title="ICW Wallet")

STATIC_DIR = Path(__file__).parent / "static"


class TransferRequest(BaseModel):
    token: str = "ckbtc"
    recipient: str
    amount: str
    subaccount: str = "0"
    from_subaccount: str = "0"
    memo: str = ""
    network: str = "ic"
    ledger: str = ""  # Custom ledger canister ID (for local testing)
    fee: Optional[int] = None  # Custom fee (for local testing)


class IdentityRequest(BaseModel):
    name: str


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/logo.png")
async def logo():
    return FileResponse(STATIC_DIR / "logo.png", media_type="image/png")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(STATIC_DIR / "logo.png", media_type="image/png")


@app.get("/api/prices")
async def get_prices():
    """Get all token prices in USD."""
    prices = get_all_prices()
    # Map coingecko IDs back to token names
    result = {}
    for token, (_, name, _, _, cg_id) in TOKENS.items():
        result[token] = {"name": name, "price": prices.get(cg_id), "coingecko_id": cg_id}
    return {"prices": result, "timestamp": __import__("time").time()}


@app.get("/api/identity")
async def get_identity():
    """Get current identity and principal."""
    ensure_dfx()
    try:
        identity = subprocess.run(
            ["dfx", "identity", "whoami"], capture_output=True, text=True, check=True
        ).stdout.strip()
        p = principal()
        return {"identity": identity, "principal": p}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/identities")
async def list_identities():
    """List all identities."""
    ensure_dfx()
    try:
        current = subprocess.run(
            ["dfx", "identity", "whoami"], capture_output=True, text=True, check=True
        ).stdout.strip()
        r = subprocess.run(["dfx", "identity", "list"], capture_output=True, text=True, check=True)
        ids = [
            {"name": line.strip(), "active": line.strip() == current}
            for line in r.stdout.strip().split("\n")
            if line.strip()
        ]
        return {"identities": ids, "current": current}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/identity/use")
async def use_identity(req: IdentityRequest):
    """Switch to a different identity."""
    ensure_dfx()
    try:
        subprocess.run(["dfx", "identity", "use", req.name], check=True)
        return {"switched": req.name, "principal": principal()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balance/{token}")
async def get_balance(token: str, network: str = "ic", subaccount: str = "0", ledger: str = ""):
    """Get token balance with USD value."""
    if token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")

    default_ledger, name, dec, _, cg_id = TOKENS[token]
    ledger_id = ledger if ledger else default_ledger
    try:
        p = principal()
        from icw.cli import subaccount as sa_fn

        bal = int(
            dfx(
                [
                    "canister",
                    "call",
                    ledger_id,
                    "icrc1_balance_of",
                    f'(record {{ owner = principal "{p}"; subaccount = {sa_fn(subaccount)}; }})',
                ],
                network,
            )
            or 0
        )
        human = bal / 10**dec
        price = get_usd_price(cg_id) if network == "ic" else None
        usd = round(human * price, 2) if price else None
        return {
            "token": name,
            "balance": human,
            "raw": bal,
            "usd": usd,
            "price": price,
            "principal": p,
            "ledger": ledger_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balances")
async def get_all_balances(network: str = "ic", ledgers: str = ""):
    """Get all token balances.

    ledgers: JSON-encoded dict of token -> ledger_id mappings (for local testing)
    """
    import json as json_lib

    ledger_map = {}
    if ledgers:
        try:
            ledger_map = json_lib.loads(ledgers)
        except Exception:
            # Ignore malformed JSON; use empty ledger map
            pass

    balances = []
    for token in TOKENS:
        try:
            custom_ledger = ledger_map.get(token, "")
            # Skip tokens without custom ledgers on local network
            if network == "local" and not custom_ledger:
                continue
            bal = await get_balance(token, network, "0", custom_ledger)
            balances.append(bal)
        except Exception:
            balances.append({"token": TOKENS[token][1], "balance": 0, "error": True})
    return {"balances": balances}


@app.post("/api/transfer")
async def transfer(req: TransferRequest):
    """Transfer tokens."""
    if req.token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {req.token}")

    default_ledger, name, dec, default_fee, _ = TOKENS[req.token]
    ledger_id = req.ledger if req.ledger else default_ledger
    fee = req.fee if req.fee is not None else default_fee
    try:
        amt = int(float(req.amount) * 10**dec) if "." in req.amount else int(req.amount)
        memo_val = memo(req.memo) if req.memo else "null"

        r = dfx(
            [
                "canister",
                "call",
                ledger_id,
                "icrc1_transfer",
                f'(record {{ to = record {{ owner = principal "{req.recipient}"; subaccount = {subaccount(req.subaccount)}; }}; amount = {amt}; fee = opt {fee}; memo = {memo_val}; created_at_time = null; from_subaccount = {subaccount(req.from_subaccount)}; }})',
            ],
            req.network,
        )

        if isinstance(r, dict) and "Ok" in r:
            result = {
                "ok": True,
                "block": r["Ok"],
                "token": name,
                "amount": amt / 10**dec,
                "to": req.recipient,
            }
            if req.memo:
                result["memo"] = req.memo
            return result
        elif isinstance(r, dict) and "Err" in r:
            return {"ok": False, "error": r["Err"]}
        else:
            return {"ok": False, "result": r}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explorer")
async def explorer():
    """Serve the explorer page."""
    return FileResponse(STATIC_DIR / "explorer.html")


@app.get("/api/account/{account}/balances")
async def get_account_balances(account: str, network: str = "ic", ledgers: str = ""):
    """Get all token balances for a specific account (principal)."""
    import json as json_lib

    ledger_map = {}
    if ledgers:
        try:
            ledger_map = json_lib.loads(ledgers)
        except Exception:
            pass

    balances = []
    for token in TOKENS:
        try:
            custom_ledger = ledger_map.get(token, "")
            if network == "local" and not custom_ledger:
                continue
            default_ledger, name, dec, _, cg_id = TOKENS[token]
            ledger_id = custom_ledger if custom_ledger else default_ledger
            from icw.cli import subaccount as sa_fn

            bal = int(
                dfx(
                    [
                        "canister",
                        "call",
                        ledger_id,
                        "icrc1_balance_of",
                        f'(record {{ owner = principal "{account}"; subaccount = {sa_fn("0")}; }})',
                    ],
                    network,
                )
                or 0
            )
            human = bal / 10**dec
            price = get_usd_price(cg_id) if network == "ic" else None
            usd = round(human * price, 2) if price else None
            balances.append(
                {
                    "token": name,
                    "balance": human,
                    "raw": bal,
                    "usd": usd,
                    "price": price,
                    "ledger": ledger_id,
                }
            )
        except Exception:
            balances.append({"token": TOKENS[token][1], "balance": 0, "error": True})
    return {"balances": balances, "account": account}


INDEX_CANISTERS = {
    "ckbtc": "n5wcd-faaaa-aaaar-qaaea-cai",
    "cketh": "s3zol-vqaaa-aaaar-qacpa-cai",
    "icp": "qhbym-qaaaa-aaaaa-aaafq-cai",
    "ckusdc": "xrs4b-hiaaa-aaaar-qafoa-cai",
    "ckusdt": "cqdrk-hyaaa-aaaar-qag5a-cai",
    "realms": "xbkkh-syaaa-aaaah-qq3ya-cai",  # Same canister provides ledger + indexer
}


@app.get("/api/transactions/{token}")
async def get_transactions(
    token: str,
    account: str = "",
    network: str = "ic",
    ledger: str = "",
    index: str = "",
    limit: int = 50,
):
    """Get transaction history for a token using the index canister."""
    if token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")

    _, name, dec, _, _ = TOKENS[token]
    index_id = index if index else INDEX_CANISTERS.get(token, "")

    if not index_id:
        if network == "local":
            return {
                "transactions": [],
                "token": name,
                "account": account if account else principal(),
                "total": 0,
                "error": "No index canister configured for local network. Add it in the Local Network Configuration panel.",
            }
        raise HTTPException(status_code=400, detail=f"No index canister for {token}")

    # Get the account to query (default to current identity)
    query_account = account if account else principal()

    try:
        # Query the index canister for account transactions
        result = dfx(
            [
                "canister",
                "call",
                index_id,
                "get_account_transactions",
                f'(record {{ account = record {{ owner = principal "{query_account}"; subaccount = null }}; start = null; max_results = {limit} : nat }})',
            ],
            network,
        )

        transactions = []

        if isinstance(result, dict):
            if "Ok" in result:
                data = result["Ok"]

                for tx_entry in data.get("transactions", []):
                    try:
                        tx_id = tx_entry.get("id", 0)
                        if isinstance(tx_id, str):
                            tx_id = int(tx_id.replace("_", ""))

                        tx = tx_entry.get("transaction", {})
                        kind = tx.get("kind", "unknown")
                        timestamp = tx.get("timestamp")
                        if isinstance(timestamp, str):
                            timestamp = int(timestamp.replace("_", ""))

                        from_account = None
                        to_account = None
                        amount = 0

                        # Parse based on transaction kind
                        if kind == "transfer" and tx.get("transfer"):
                            transfer = tx["transfer"]
                            if isinstance(transfer, list) and len(transfer) > 0:
                                transfer = transfer[0]

                            if "from" in transfer:
                                from_acc = transfer["from"]
                                from_account = from_acc.get("owner", "")
                            if "to" in transfer:
                                to_acc = transfer["to"]
                                to_account = to_acc.get("owner", "")

                            amt = transfer.get("amount", "0")
                            amount = int(str(amt).replace("_", ""))

                        elif kind == "mint" and tx.get("mint"):
                            mint = tx["mint"]
                            if isinstance(mint, list) and len(mint) > 0:
                                mint = mint[0]

                            if "to" in mint:
                                to_acc = mint["to"]
                                to_account = to_acc.get("owner", "")

                            amt = mint.get("amount", "0")
                            amount = int(str(amt).replace("_", ""))

                        elif kind == "burn" and tx.get("burn"):
                            burn = tx["burn"]
                            if isinstance(burn, list) and len(burn) > 0:
                                burn = burn[0]

                            if "from" in burn:
                                from_acc = burn["from"]
                                from_account = from_acc.get("owner", "")

                            amt = burn.get("amount", "0")
                            amount = int(str(amt).replace("_", ""))

                        transactions.append(
                            {
                                "block": tx_id,
                                "type": kind,
                                "from": from_account,
                                "to": to_account,
                                "amount": amount / 10**dec,
                                "amount_raw": amount,
                                "timestamp": timestamp,
                            }
                        )

                    except Exception:
                        continue

            elif "Err" in result:
                raise HTTPException(status_code=400, detail=str(result["Err"]))

        return {
            "transactions": transactions,
            "token": name,
            "account": query_account,
            "total": len(transactions),
            "index": index_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/{token}")
async def get_info(token: str, network: str = "ic"):
    """Get token info."""
    if token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")

    ledger, name, dec, fee, cg_id = TOKENS[token]
    price = get_usd_price(cg_id)
    try:
        user_principal = principal()
    except Exception:
        user_principal = None
    return {
        "token": name,
        "ledger": ledger,
        "decimals": dec,
        "fee": fee,
        "fee_human": fee / 10**dec,
        "price_usd": price,
        "principal": user_principal,
        "network": network,
    }


# Global config set by run_server
_server_config = {"network": "ic", "ledgers": {}}


def get_version_info():
    """Get version, git commit, and build date."""
    import subprocess
    from icw import __version__

    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=STATIC_DIR.parent
            ).stdout.strip()
            or "unknown"
        )
    except Exception:
        commit = "unknown"

    try:
        date = (
            subprocess.run(
                ["git", "log", "-1", "--format=%ci"], capture_output=True, text=True, cwd=STATIC_DIR.parent
            ).stdout.strip()
            or "unknown"
        )
    except Exception:
        date = "unknown"

    return {"version": __version__, "commit": commit, "date": date}


@app.get("/api/config")
async def get_config():
    """Get server configuration (network, ledgers, version)."""
    return {**_server_config, **get_version_info()}


def run_server(
    port: int = 5555,
    open_browser: bool = True,
    network: str = "ic",
    ledgers: dict = None,
):
    """Start the web UI server."""
    global _server_config
    _server_config = {"network": network, "ledgers": ledgers or {}}

    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
