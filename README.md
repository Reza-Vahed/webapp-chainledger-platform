# ChainLedger Platform - On-Chain Data Import Agent (MVP)

[![GitHub release](https://img.shields.io/github/v/release/Reza-Vahed/webapp-chainledger-platform)](https://github.com/Reza-Vahed/webapp-chainledger-platform/releases/tag/v1.0.0)

🇩🇪 [Deutsche Version](README.de.md)

A read-only CLI + web tool that pulls on-chain transaction data directly
from public EVM wallet addresses (Ethereum Mainnet, Arbitrum One),
normalizes it into a canonical model, classifies it into a fixed
tax-relevant category list, flags obvious data issues, and exports it as
CSV + JSON for manual reconciliation with crypto tax tools (e.g.
Blockpit, CoinTracking).

This is a portfolio / technical-validation project, **not** tax software.

## What this tool does NOT do

- No user accounts/auth, no external DB server, no AI components (MVP scope)
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

### Multi-chain support

Two chains are currently supported: **Ethereum Mainnet** (default) and
**Arbitrum One**, selectable via `--chain` (CLI) or the chain dropdown
(web UI). Both are served by the *same* `EtherscanClient`, parametrized
via a small chain registry (`src/api_client/chains.py`) - Etherscan API
V2 covers both chains (and 50+ other EVM chains) under the same endpoint
and API key, so no second client implementation or extra API key is
needed. Classification logic is unchanged and chain-agnostic; only the
native gas token symbol/decimals and the known-contract allowlists
(`src/classifier.py`) are chain-scoped, so a Mainnet contract address
can never be mistaken for an unrelated contract on another chain. See
`docs/adr/0004-multi-chain-support.md` for the full comparison
(Arbitrum vs. Polygon) and the live rate-limit verification.

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

81 automated tests cover the API client (pagination, rate-limit retry,
error handling), normalizer, classifier, validator, exporter, the
raw-data persistence hook, the chain registry, and the SQLite-backed job
store (`api/db.py`).

## Example invocation

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
```

Same wallet on Arbitrum One instead of Ethereum Mainnet:

```bash
python -m src.cli 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain arbitrum
```

Multiple wallets in one run:

```bash
python -m src.cli 0xAddress1... 0xAddress2...
```

Optional flags: `--chain` (`ethereum` default, or `arbitrum`),
`--env-file`, `--raw-dir`, `--processed-dir`, `--log-dir` (defaults to
`data/raw/`, `data/processed/`, `data/logs/` in the project root - see
`python -m src.cli --help`).

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

### Second example: a small wallet (fast comparison run)

`0x7e2d0fe0ffdd78c264f8d40d19acb7d04390c6e8` - a counterparty address that
shows up in vitalik.eth's earliest (2015) on-chain history, i.e. a
real, publicly verifiable address, just far less active.

**Verified with a real run (2026-07-13): 26 transactions**, finished in
about 1 second (each category fit on a single page, no pagination or
rate-limiting involved) - `9` Contract-Interaktion, `8` Transfer-Out, `8`
Unklassifiziert, `1` Transfer-In.

Notably, the `Unklassifiziert` share here is much higher (~31%) than for
vitalik.eth (~0.17%). This is intentional, conservative behavior, not a
bug: most of the flagged rows are incoming ETH transfers that also carry
non-empty input data on a "normal" transaction - a pattern more common in
early (2015-era) Ethereum usage. Since we can't be sure such a record is
"just" a transfer versus something else, the classifier refuses to guess
and flags it `manual_review_required` instead. vitalik.eth's much lower
rate simply reflects that most of its transactions are either plain ETH
transfers (empty input data) or clearly recognizable swap patterns.

Good illustration of why a single "moderate" test address isn't enough on
its own to judge classification quality - activity patterns vary a lot
by wallet age and usage style.

### Arbitrum One acceptance test (same addresses, different chain)

EOA addresses are identical across EVM chains, so both addresses above
were re-verified with a real run against **Arbitrum One**
(`--chain arbitrum`) instead of hunting for new reference addresses.

**`vitalik.eth`, verified with a real run (2026-07-15): 20,070
transactions** processed end-to-end in about 11 seconds (20,038
Transfer-In, 10 Swap, 3 Contract-Interaktion, 2 Transfer-Out, 17
Unklassifiziert). Much lower volume than on Mainnet (446,829 there),
consistent with this address being far more Mainnet-native - but still
enough to exercise pagination for real: the `normal` and `tokentx`
categories both hit Etherscan's 10,000-record pagination window and
triggered a `startblock` shift (`src/api_client/etherscan_client.py`),
confirming that mechanism works unchanged on a second chain. No
rate-limit retries were needed in this single-threaded CLI run.

**Small wallet `0x7e2d0fe0ffdd78c264f8d40d19acb7d04390c6e8`, verified
with a real run (2026-07-15): 7 transactions** (6 Contract-Interaktion,
1 Unklassifiziert) - finished in about 1 second, single page per
category, no pagination or rate-limiting involved.

## Web Frontend (Phase 2 + 3)

A React + TypeScript SPA (`frontend/`) sits on top of a thin FastAPI wrapper
(`api/`) around the same pipeline described above - no logic is duplicated;
CLI and web app share `src/` unchanged.

- **Trilingual UI** (German/English/Farsi) with a language switcher.
  Default language: German. Farsi renders right-to-left (`dir="rtl"`),
  including mirrored table columns and direction-appropriate pagination
  arrows. Dates are always shown in the Gregorian calendar with Western
  digits in every language (forced via a Unicode locale extension) so the
  displayed dates always match the Gregorian timestamps in the CSV/JSON
  exports - the browser's default for `fa` would otherwise silently switch
  to the Persian calendar and Persian digits, which would be confusing to
  cross-reference against the export files.
- Light/dark theme toggle (persisted in `localStorage`).
- Enter a wallet address, pick a chain (Ethereum Mainnet or Arbitrum One)
  from the dropdown, watch live per-category progress (polling every
  1.5 s - chosen over SSE/WebSocket as the simplest robust option for an
  MVP), then browse results in a paginated, filterable, sortable table
  with CSV/JSON download links.
- **Import history**: a list of past imports (any chain, any state) with
  the ability to reopen a completed import's results or delete it
  (removes the database row and the associated raw/export files; blocked
  while a job is still running). Survives backend restarts - see
  "Persistence" below.
- The Etherscan API key never reaches the browser - only the FastAPI
  backend talks to Etherscan, using the same `.env` as the CLI.

### Backend setup

```bash
source .venv/bin/activate               # from the project root
pip install -r requirements-dev.txt     # includes fastapi, uvicorn, httpx
uvicorn api.main:app --reload --port 8000
```

### Frontend setup

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_BASE_URL, default http://localhost:8000
npm run dev
```

Open http://localhost:5173/. Both servers must run at the same time (two
separate processes in this MVP - no combined single-command startup yet,
and no Docker packaging yet either, though `api/` and `frontend/` are kept
as separate directories/processes specifically so that's a small addition
later rather than a restructure).

### API endpoints (backend)

| Method & path | Purpose |
|---|---|
| `POST /api/v1/imports` | Start an import job for one or more addresses (`chain`: `ethereum` default or `arbitrum`) |
| `GET /api/v1/imports` | Import history (all chains, all states), newest first |
| `GET /api/v1/imports/{id}` | Job status + per-category progress (for polling) |
| `GET /api/v1/imports/{id}/transactions` | Paginated/filtered/sorted results |
| `GET /api/v1/imports/{id}/export/{csv,json}` | Download the generated export |
| `DELETE /api/v1/imports/{id}` | Delete a completed/failed import (`409` while still running) |

### Persistence

Job metadata (chain, addresses, state, timestamps, counts) is written to
a local SQLite database (`data/chainledger.db`, git-ignored) on every
state transition. The validated transactions themselves are **not**
duplicated in the database - they already live in
`data/processed/transactions_<job_id>.json` (see "Output" above) and are
read back from there when a completed import is reopened after a
restart. Verified against a real backend process kill + restart, not
just an in-process simulation - see
`docs/adr/0005-persistence.md` for the full comparison against a
file-based alternative and the reasoning.

Retention is manual-only by design: completed imports stay until
explicitly deleted via the API/UI - no automatic expiry, no background
scheduler (would be over-engineering for a single-user tool). Deleting a
running job is rejected (`409`) to avoid racing its writer thread.

Known remaining MVP limitation (documented, not solved): a single
process holds the currently-running jobs in memory (no multi-worker
support), and a job that was `running` at the moment of an unexpected
backend crash stays stuck at `running` in the history afterwards (no
recovery heuristic). Acceptable for a single-user demo tool without
accounts.

### Backend tests

```bash
pytest tests/test_api_imports.py tests/test_cli.py tests/test_job_store.py tests/test_chains.py -v
```

Uses FastAPI's `TestClient` with a fake Etherscan client - no network
calls, no API key needed to run these.

## Data & privacy (GDPR)

Everything runs and stays local. `data/raw/`, `data/processed/`, and the
job-history database (`data/chainledger.db`) are git-ignored by default
since they may contain wallet-linked transaction data. No credentials
other than your own Etherscan API key (via `.env`, never committed) are
stored anywhere - this applies identically to the CLI and the web
backend, which read the same `.env` file. The same key covers every
supported chain (see "Multi-chain support" above), so no new secret is
introduced by adding Arbitrum. Import history is retained until manually
deleted (see "Persistence" above) - no automatic unlimited retention by
design.

## Documentation

- Architecture Decision Records: `docs/adr/0001-tech-stack.md`,
  `0002-api-choice.md`, `0003-output-format.md`,
  `0004-multi-chain-support.md`, `0005-persistence.md`
