#!/usr/bin/env python3
"""ICW Web API - FastAPI server for the wallet UI."""
import subprocess
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from icw.cli import (
    TOKENS,
    dfx,
    ensure_dfx,
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


class IdentityRequest(BaseModel):
    name: str


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


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
        r = subprocess.run(
            ["dfx", "identity", "list"], capture_output=True, text=True, check=True
        )
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
async def get_balance(token: str, network: str = "ic", subaccount: str = "0"):
    """Get token balance with USD value."""
    if token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")

    ledger, name, dec, _, cg_id = TOKENS[token]
    try:
        p = principal()
        from icw.cli import subaccount as sa_fn
        bal = int(
            dfx(
                [
                    "canister",
                    "call",
                    ledger,
                    "icrc1_balance_of",
                    f'(record {{ owner = principal "{p}"; subaccount = {sa_fn(subaccount)}; }})',
                ],
                network,
            )
            or 0
        )
        human = bal / 10**dec
        price = get_usd_price(cg_id)
        usd = round(human * price, 2) if price else None
        return {
            "token": name,
            "balance": human,
            "raw": bal,
            "usd": usd,
            "price": price,
            "principal": p,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balances")
async def get_all_balances(network: str = "ic"):
    """Get all token balances."""
    balances = []
    for token in TOKENS:
        try:
            bal = await get_balance(token, network)
            balances.append(bal)
        except Exception:
            balances.append({"token": token, "error": True})
    return {"balances": balances}


@app.post("/api/transfer")
async def transfer(req: TransferRequest):
    """Transfer tokens."""
    if req.token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {req.token}")

    ledger, name, dec, fee, _ = TOKENS[req.token]
    try:
        amt = int(float(req.amount) * 10**dec) if "." in req.amount else int(req.amount)
        memo_val = memo(req.memo) if req.memo else "null"

        r = dfx(
            [
                "canister",
                "call",
                ledger,
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


@app.get("/api/info/{token}")
async def get_info(token: str, network: str = "ic"):
    """Get token info."""
    if token not in TOKENS:
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")

    ledger, name, dec, fee, cg_id = TOKENS[token]
    price = get_usd_price(cg_id)
    return {
        "token": name,
        "ledger": ledger,
        "decimals": dec,
        "fee": fee,
        "fee_human": fee / 10**dec,
        "price_usd": price,
        "principal": principal(),
        "network": network,
    }


def run_server(port: int = 5555, open_browser: bool = True):
    """Start the web UI server."""
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
