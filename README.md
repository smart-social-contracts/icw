# ICW - ICP Wallet CLI

Simple CLI for managing ICRC-1 tokens (ckBTC, ckETH, ICP) on the Internet Computer.

## Install

```bash
pip install icw
```

## Usage

```bash
# Check balance (auto-converts to USD)
icw balance
icw balance -t cketh
icw balance -p <principal> -s 1  # specific principal + subaccount

# Transfer tokens
icw transfer <recipient> 0.001
icw transfer <recipient> 0.001 -s 1 -f 2  # to subaccount 1, from subaccount 2

# Token info + current price
icw info
icw info -t icp
```

## Output

All commands output JSON for easy parsing:

```json
{
  "token": "ckBTC",
  "balance": 0.001,
  "raw": 100000,
  "usd": 97.0,
  "price": 97000.0,
  "principal": "abc-xyz"
}
```

## Options

- `-t, --token`: Token (ckbtc, cketh, icp). Default: ckbtc
- `-n, --network`: Network (ic, local). Default: ic

## Requirements

- Python 3.9+
- dfx (auto-installs if missing)
