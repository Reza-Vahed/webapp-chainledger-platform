# ChainLedger Platform - On-Chain Data Import Agent (MVP)

🇩🇪 [Deutsche Version](README.de.md)

A read-only CLI tool that pulls on-chain transaction data directly from
public Ethereum wallet addresses, normalizes it into a canonical model,
classifies it into a fixed tax-relevant category list, flags obvious
data issues, and exports it as CSV + JSON for manual reconciliation with
crypto tax tools (e.g. Blockpit, CoinTracking).

This is a portfolio / technical-validation project, **not** tax software.

## What this tool does NOT do

- No UI, no database, no multi-chain support, no AI components (MVP scope)
- No tax calculation, no FIFO/cost-basis logic - it only prepares data
- No NFT transfers (ERC-721/1155) - out of MVP scope
- Never signs or sends transactions; never touches private keys, seed
  phrases, or exchange credentials - strictly read-only, public data only
- Never guesses: ambiguous cases (e.g. buy/sell direction of a DEX swap)
  are always classified as `Swap` or `Unclassified`, never silently assumed

## Architecture

```
EtherscanClient (src/api_client/)  ->  raw JSON (data/raw/, unmodified)
        |
        v
normalize_transactions (src/normalizer.py)  ->  CanonicalTransaction (pydantic)
        |
        v
classify_transactions (src/classifier.py)   ->  fixed category + confidence
        |
        v
validate_transactions (src/validator.py)    ->  flags obvious errors/gaps
        |
        v
export_transactions (src/exporter.py)       ->  data/processed/*.csv + *.json
```

Orchestrated by `src/cli.py`. The data source is abstracted behind
`BlockchainDataSource` (`src/api_client/base.py`) so Etherscan can be
swapped for another provider later without touching the rest of the
pipeline. See `docs/adr/` for the reasoning behind these decisions.

## Classification categories

Fixed, exhaustive list (see `src/models.py::TxCategory`):
`Transfer-In`, `Transfer-Out`, `Swap`, `Staking-Reward`, `Airdrop`,
`Contract-Interaktion`, `Unklassifiziert`.

- **Swap detection** groups all records sharing a `tx_hash` and looks for
  multi-leg patterns (e.g. ERC-20 out + ETH in). Buy/sell direction is
  never inferred.
- **Staking-Reward / Airdrop** are only assigned on a match against a
  small, explicit allowlist of known contracts (`src/classifier.py`).
  Everything else stays `Transfer-In`/`Unklassifiziert` rather than being
  guessed. Known limitation: rebasing liquid-staking tokens (e.g. stETH)
  don't always emit classic transfer events, so rewards from those may
  not be fully captured via the account API - flag for manual review.
- Every row carries `confidence` (0.0-1.0) and a `warnings` list (e.g.
  `manual_review_required`, `data_gap_or_error`) - never silently dropped.

## Requirements

- Python 3.11+
- Free Etherscan API key: https://etherscan.io/apis

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env
# then edit .env and set ETHERSCAN_API_KEY=<your key>
```

## Running the tests

```bash
pytest tests/ -v
```

40 automated tests cover the API client (pagination, rate-limit retry,
error handling), normalizer, classifier, validator, exporter, and the
raw-data persistence hook.

## Example invocation

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
```

Multiple wallets in one run:

```bash
python -m src.cli 0xAddress1... 0xAddress2...
```

Optional flags: `--env-file`, `--raw-dir`, `--processed-dir`, `--log-dir`
(defaults to `data/raw/`, `data/processed/`, `data/logs/` in the project
root - see `python -m src.cli --help`).

Output:
- `data/raw/<run_id>_<address>_<category>_page<N>.json` - unmodified raw
  API responses (audit trail, requirement: never mutate the source data)
- `data/processed/transactions_<run_id>.csv` and `.json` - normalized,
  classified, validated transactions
- `data/logs/run_<run_id>.log` - API calls, rate-limit events, warnings

### Documented test address (acceptance test)

`0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045` (`vitalik.eth`) - one of the
most publicly documented Ethereum addresses (ENS-linked, widely cited).

**Verified with a real run (2026-07-13):** this address turned out to be
far more active than "moderate" - **446,829 transactions** processed
end-to-end without errors (254,699 Transfer-In, 174,330 Transfer-Out,
11,939 Swap, 5,090 Contract-Interaktion, 771 Unklassifiziert). The first
live run actually surfaced a real bug: Etherscan's free tier enforced
`3 req/s` in practice (not the `5 req/s` we had assumed from the docs),
and our rate-limit detection only matched the exact phrase
`"Max rate limit reached"`, missing the real-world variant
`"Max calls per sec rate limit reached (3/sec)"`. This caused already
page 10 of 9,000+ fetched records to be discarded instead of retried.
Fixed by broadening the match and lowering the default to `3 req/s`
(see `docs/adr/0002-api-choice.md` and `src/api_client/etherscan_client.py`).
A high-volume address like this one is actually a good stress test for
pagination and rate-limit handling for exactly this reason.

If you prefer a faster smoke test, use any wallet address of your own
choosing with a lower transaction count - check the count on the address's
Etherscan page before running (`https://etherscan.io/address/<address>`,
"Transactions" tab).

## Data & privacy (GDPR)

Everything runs and stays local. `data/raw/` and `data/processed/` are
git-ignored by default since they may contain wallet-linked transaction
data. No credentials other than your own Etherscan API key (via `.env`,
never committed) are stored anywhere.

## Documentation

- Architecture Decision Records: `docs/adr/0001-tech-stack.md`,
  `0002-api-choice.md`, `0003-output-format.md`
