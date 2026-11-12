# Input audit for evm-cluster-check

`evm-cluster-check` builds address clusters from three days of Ethereum mainnet data: blocks
26,316,189–26,337,722 (1–3 November 2026 UTC). A missing or altered `Transfer` log there would add or
drop an edge in its graph, so its inputs were checked with this tool before its results were read.

## 1. Are the blocks provable, and what does each provider return?

`chain-evidence --chain ethereum audit --from 26316189 --to 26337722 --sample 40 --seed 7`

| Check | Result |
|---|---|
| Blocks sampled (uniform, seed 7) | 40 |
| Blocks whose header hash, `transactionsRoot` and `receiptsRoot` all reproduced | **40/40** (receipts served by drpc; block hash identical across every answering provider) |
| `Transfer` logs inside the proven receipts | 19,640 |
| drpc `eth_getLogs` (single block, `Transfer` topic) vs proven receipts | **40/40 blocks identical** |
| publicnode `eth_getLogs` | refused for 40/40 (`Archive requests require a personal token`) |
| publicnode `eth_getBlockReceipts` at this depth | `null` (success, no data); see `docs/what-went-wrong.md` §2 |
| 1rpc | refused for 40/40 (daily quota reached at the time) |

This is why `evm-cluster-check` fetches its logs from drpc. The public publicnode endpoint cannot serve this
window, and at this depth it fails *silently* for receipts.

## 2. Does the stored dataset match the proven receipts?

`scripts/audit_evm_dataset.py` compares the Parquet rows `evm-cluster-check` wrote (block, tx hash, log index,
token, from, to, value) with the `Transfer` logs extracted from receipts that reproduce `receiptsRoot`.

| Blocks | Proven `Transfer` logs | Missing from dataset | Extra in dataset | Field mismatch |
|---|---|---|---|---|
| 40 | 19,640 | 0 | 0 | 0 |

**Verdict:** for every audited block the input data is complete and unaltered. The proof does not depend
on trusting drpc, even though drpc both served the dataset and supplied the receipts for the proof. The
receipts had to reproduce the header's `receiptsRoot`, and the header had to hash to the block hash that
all providers agreed on.

**Limits.** This is a sample: 40 of 21,534 blocks. With zero failures in 40 blocks, the 95 %
upper bound on the share of bad blocks is about 7.5 % (rule of three), not zero.
Re-running the audit over every block is a matter of time, not code.
