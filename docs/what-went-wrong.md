# What went wrong

Everything here happened while building and running this study. Nothing below is hypothetical.

## 1. I deleted a piece of evidence

During the first smoke test (4 ranges), 1rpc answered an `eth_getLogs` query for the Uniswap v3
USDC/WETH pool over 25 finalised blocks (26,344,681–26,344,705) with **an empty success**: `[]`, no
error. drpc returned 21 logs, and the adjudicator rebuilt the true set from drpc's receipts, verified
against `receiptsRoot` and the block hash: **21 logs**. That is exactly the silent-miss failure this
tool exists to catch.

I then reset `results/` to start a clean survey and deleted the bundle along with the smoke-test rows.
Six replays of the same query to 1rpc afterwards produced only errors (`method not available`,
HTTP 429, a relayed `Archive requests require a personal token`, `This endpoint has been
discontinued.`), never a second empty success. So the observation is recorded here from my notes,
not as a bundle, and it is **not counted** in any table.

*Fix:* the survey now writes each row and bundle the moment it completes, and I no longer clear
`results/` by hand.

## 2. My first probe said "publicnode serves receipts deep" — it was checking the wrong thing

The depth probe tested `answer.ok`. publicnode answers `eth_getBlockReceipts` for blocks older than
about 42,000–45,000 blocks (roughly six days) with `result: null` — a *success with no data* — and
`eth_getTransactionReceipt` for transactions in those blocks also returns `null`, while
`eth_getTransactionByHash` still returns the transaction and its block number. A reader would
conclude "this transaction has no receipt". I found this only because the transaction survey flagged
a receipt disagreement (`null_from: publicnode`).

*Fix:* `verify-receipts` now reports `null result for eth_getBlockReceipts (success, no data)` as its
own outcome, and the transaction survey records which provider returned a null receipt and how deep
the block was.

## 3. The first survey design did not fit what providers accept

The first plan used 50-block windows over the last ~7 days. publicnode refused anything older than
~5,000–10,000 blocks for `eth_getLogs` (and any multi-block query without an `address`), and 1rpc
refused anything over 25 blocks on some backends. Most of the first run would have been refusals,
not comparisons. I discarded that run (it was never mixed into results) and redesigned the survey:
ranges of 1, 10 or 25 blocks, a recent window every provider serves, and a separate `final_deep`
stratum to measure behaviour on older history.

## 4. Retries were too slow, and an interrupted run would lose everything

Exponential back-off up to 30 s with 5 attempts made one failing provider cost ~60 s per range, and
rows were written only at the end of a run. I stopped the run, capped back-off at 8 s and 4
attempts, and switched to per-row writes.

## 5. Only two Ethereum providers were really in play

The plan was three independent keyless providers. 1rpc's free quota ("You've reached the usage limit
for your current plan") ran out during the first survey. Before that, about 1 in 5 of its
`eth_getLogs` calls succeeded. 1rpc also relays at least one other provider's backend (it returned
publicnode's own archive-refusal text), so it is not fully independent of publicnode. Most Ethereum
comparisons are therefore **publicnode vs drpc**. The tables count how many answers each range really
had. Adding Alchemy and Infura keys (`providers.toml`) and re-running would fix this.

## 6. Base: one public endpoint refuses `eth_getLogs` entirely

`mainnet.base.org` answered every `eth_getLogs` with HTTP 429 `request limit reached` (rate limit
header `5;w=1`, remaining 0), even one request every three seconds, while it serves
`eth_getBlockReceipts` and `eth_blockNumber`. With 1rpc's quota gone too, a Base `eth_getLogs`
cross-provider comparison had only one answering provider. I changed the Base measurement to what *can*
be checked: per-provider receipt and header proofs, and publicnode's `eth_getLogs` against receipts
proven from either provider.

## 7. A survey column was computed wrongly in run 1

`providers_ok` counted only providers that took part in a comparison, so ranges with exactly one
answer showed `0`. The report now derives answer counts from the per-provider error map, and the
code was fixed for later runs.

## 8. Two processes, two CSV layouts

I added columns to the transaction and root surveys while an older process was still running, so
two layouts ended up in one CSV. I repaired the file by column count (`scripts/repair_csv.py`), and
`_append` now rewrites a file with the union of columns whenever the schema changes, with a test.

## 9. A survey process died without a trace

The first Base receipt-proof run stopped after 15 of 25 blocks. There was no traceback, no
out-of-memory message in the kernel log, and it was not killed by the survey's own retry logic. Because
that survey wrote its CSV only at the end, the 15 blocks were lost and had to be re-run (the 25 Base
blocks in the results are from the re-run). Every survey now writes each row as it completes.

## 10. 1rpc's `finalized` tag is stale on both chains

On Ethereum it sat at block 26,394,543 for at least 40 minutes while publicnode and drpc advanced. On
Base, heads sampled every two minutes showed 1rpc's `finalized` frozen at 56,251,175 across many
consecutive samples while the other two moved together. My finality rule takes the *lowest*
`finalized` head, so a stale tag makes comparisons more conservative, never less. But a tool that
trusted 1rpc's tag alone would treat fresh blocks as unfinalised for an hour or more.

## 11. Smaller things

- drpc's refusal says "ranges over 10000 blocks are not supported on free plan", but it refuses a
  500-block range. The enforced limit (between 100 and 500 blocks) does not match the message.
- The 1rpc transaction case: for one transaction only ~20,700 blocks (~2.9 days) old, 1rpc returned a
  `null` receipt while publicnode and drpc both returned it. So `null` receipts are not only a
  six-day-history effect at publicnode.
- Error classification is by message text. A provider that invents a new wording for "rate limited"
  would be filed as a policy refusal until the list is updated. It would never be filed as a
  disagreement.
- I could not record the terminal demo with asciinema in this environment, so the demo SVG is
  rendered from real command output by `scripts/term_svg.py`.
