# Method

## What is compared

For one question (an `eth_getLogs` filter, a block header, a transaction and its receipt) the same
JSON-RPC request goes to every configured provider in parallel. Each provider is paced separately
(≥1 s between requests, 1.5 s for 1rpc) and retried on transient failures.

**Error versus answer.** A response is an *answer* only if it carries a JSON-RPC `result`. Everything
else is an *error*, in one of two classes:

| Class | Examples (verbatim from providers) | Handling |
|---|---|---|
| transient | HTTP 429/5xx, `Rate limit exceeded`, `method not available`, `Remote Error`, empty body | retried up to 4 times with back-off; if still failing, recorded as *failed* |
| policy | `Archive requests require a personal token`, `eth_getLogs is limited to 0 - 50 blocks range`, `log query range must not exceed 25 blocks`, `Please specify an address`, `You've reached the usage limit for your current plan` | not retried; recorded as *refused* |

Neither class is ever counted as a disagreement. A disagreement needs at least two answers.

**Normalisation.** Logs are lower-cased, quantities parsed to integers, sorted by
`(blockNumber, logIndex)` and keyed by `(blockHash, transactionHash, logIndex)`. For each provider I
count logs **missing** (returned by another provider but not this one) and **content mismatches** (same
key, different address/topics/data/indices/`removed`). Headers are compared field by field.
`totalDifficulty` and `size` are skipped as provider-computed, and fields that only some providers
include are listed separately as presentation differences.

## Finality

Each provider's `finalized` head is read at the start of a run (and again before each near-head
query). A block counts as final only if it is at or below the **lowest** `finalized` head reported by
any provider. Ranges ending above that floor are "near head": they are measured, but reported in their
own column and never adjudicated, because lag between providers is expected there.

On Base the same rule uses the OP Stack `finalized` head, which follows L1 finality of the batch
(see reading notes §4).

## Proof: who is right?

When finalised providers disagree, comparison alone cannot say who is wrong. `adjudicate_logs`
rebuilds the true answer from the block's own commitments, for every block in the range:

1. All providers are asked for the block hash; the proof is accepted only if one provider's header
   **hashes to that hash** (`keccak256(rlp(header))`, fork-aware field list, tested on real blocks).
2. That provider's full transaction list must reproduce **`transactionsRoot`** (types 0, 1, 2, 3, 4 and
   OP deposit `0x7e` encoded per EIP-2718/EIP-1559/EIP-4844/EIP-7702 and the OP deposit spec).
3. Its receipts must reproduce **`receiptsRoot`** (Merkle-Patricia trie keyed by `rlp(index)`).
4. The filter is applied to the logs inside the proven receipts. That set is complete by construction.
   Each provider's original answer is then diffed against it.

The same machinery powers `verify-receipts`. For one block and each provider separately, it checks
whether that provider's data reproduces all three commitments, and whether the provider's own
`eth_getLogs` for the block matches its proven receipts (the failure mode in Erigon #23062).

## Survey design

Each `survey` run draws ranges from a random generator seeded with the run id:

| Share | Kind | Window | Shapes |
|---|---|---|---|
| 75 % | `final` | the last ~4,500 finalised blocks on Ethereum (~15 h), 20,000 on Base | 30 % single block, no filter; 70 % one token contract (USDT, USDC, WETH, DAI, LINK, a Uniswap v3 pool / Base USDC, WETH, USDbC, DAI) over 1, 10 or 25 blocks, half also filtered on the ERC-20 `Transfer` topic |
| 25 % | `final_deep` | 9,000–50,000 blocks back (Ethereum), 40,000–300,000 (Base) | same shapes |
| extra | `near_head` | the provider-reported tip, 0–2 blocks back | single block or one token, single block |

The shapes are the ones every provider accepts (see below). Single-block ranges also get a header
comparison. Disagreeing ranges and the first two agreeing ranges of each run are saved as evidence
bundles.

Rates are reported as *disagreeing comparable finalised ranges / comparable finalised ranges*, with a
95 % Wilson score interval. Runs were repeated at different times of day.

## Provider policies measured (November 2026)

| Provider | `eth_getLogs` shape limits | History | Other |
|---|---|---|---|
| publicnode (Ethereum) | multi-block queries need an `address`; single block unfiltered allowed | `eth_getLogs` refused beyond roughly 5,000–10,000 blocks ("Archive requests require a personal token"); `eth_getBlockReceipts` served much deeper | supports `eth_getBlockReceipts` |
| drpc (free) | address-filtered ranges: 100 blocks accepted, 500 refused with the message "ranges over 10000 blocks are not supported on free plan" (the stated limit does not match the enforced one) | deep history served | supports `eth_getBlockReceipts`; raw-tx methods "not available on free plan" |
| 1rpc | the range cap message varies by backend: "0 - 50 blocks", "must not exceed 25 blocks", and "You can make eth_getLogs requests with up to a 10 block range. Based on your parameters, this block range should work: [...]" | relays publicnode's own archive refusal verbatim, and other backends' messages, so it is **not independent** of the providers it routes to | `eth_getBlockReceipts` "not allowed"; intermittent `method not available` and `Remote Error`; daily quota exhausted during this study; once replied "This endpoint has been discontinued."; its `finalized` tag stayed at 26,394,543 for at least 40 minutes while the others advanced |
| Base providers | see `results/` | | deposit receipts include `depositNonce`/`depositReceiptVersion` |

## Evidence bundle

`bundle.py` writes JSON containing the exact request, every provider's raw answer or error, send and
receive timestamps, latency, the endpoint with any key-like path segment redacted, a SHA-256 of each
canonicalised result, the comparison, the finality context and any proof. `bundle_sha256` covers all of
it. `chain-evidence verify-bundle` recomputes both levels of hash, and CI re-verifies every published
bundle on every push.

## Reproduce

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install -e .
pytest -q                                     # offline
chain-evidence --chain ethereum survey --ranges 200 --near-head 30 --tx-sample 50 --root-sample 20
chain-evidence --chain base survey --ranges 120 --near-head 20 --tx-sample 30 --root-sample 15
python -m chain_evidence.report               # tables, charts, results/summary.json
```
