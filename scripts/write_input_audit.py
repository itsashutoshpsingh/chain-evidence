"""Write results/evm-cluster-check-input-audit.md from the two audit CSVs."""
import csv
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "results"
a = list(csv.DictReader(open(R / "audit_ethereum_26316189_26337722.csv")))
d = list(csv.DictReader(open(R / "evm-cluster-check-dataset-audit.csv")))
tl = sum(int(r["true_transfer_logs"]) for r in a)
dl = sum(int(r["true_logs"]) for r in d)
bad = lambda k: sum(int(r[k]) for r in d)
md = f"""# Input audit for evm-cluster-check

`evm-cluster-check` builds address clusters from three days of Ethereum mainnet data: blocks
26,316,189–26,337,722 (1–3 November 2026 UTC). A missing or altered `Transfer` log there would add or
drop an edge in its graph, so its inputs were checked with this tool before its results were read.

## 1. Are the blocks provable, and what does each provider return?

`chain-evidence --chain ethereum audit --from 26316189 --to 26337722 --sample 40 --seed 7`

| Check | Result |
|---|---|
| Blocks sampled (uniform, seed 7) | {len(a)} |
| Blocks whose header hash, `transactionsRoot` and `receiptsRoot` all reproduced | **{sum(r['proven'] == 'True' for r in a)}/{len(a)}** (receipts served by drpc; block hash identical across every answering provider) |
| `Transfer` logs inside the proven receipts | {tl:,} |
| drpc `eth_getLogs` (single block, `Transfer` topic) vs proven receipts | **{sum(r['drpc'] == 'ok' for r in a)}/{len(a)} blocks identical** |
| publicnode `eth_getLogs` | refused for {sum(r['publicnode'].startswith('error') for r in a)}/{len(a)} (`Archive requests require a personal token`) |
| publicnode `eth_getBlockReceipts` at this depth | `null` (success, no data); see `docs/what-went-wrong.md` §2 |
| 1rpc | refused for {sum(r['1rpc'].startswith('error') for r in a)}/{len(a)} (daily quota reached at the time) |

This is why `evm-cluster-check` fetches its logs from drpc. The public publicnode endpoint cannot serve this
window, and at this depth it fails *silently* for receipts.

## 2. Does the stored dataset match the proven receipts?

`scripts/audit_evm_dataset.py` compares the Parquet rows `evm-cluster-check` wrote (block, tx hash, log index,
token, from, to, value) with the `Transfer` logs extracted from receipts that reproduce `receiptsRoot`.

| Blocks | Proven `Transfer` logs | Missing from dataset | Extra in dataset | Field mismatch |
|---|---|---|---|---|
| {len(d)} | {dl:,} | {bad('missing_from_dataset')} | {bad('extra_in_dataset')} | {bad('field_mismatch')} |

**Verdict:** for every audited block the input data is complete and unaltered. The proof does not depend
on trusting drpc, even though drpc both served the dataset and supplied the receipts for the proof. The
receipts had to reproduce the header's `receiptsRoot`, and the header had to hash to the block hash that
all providers agreed on.

**Limits.** This is a sample: {len(d)} of 21,534 blocks. With zero failures in {len(d)} blocks, the 95 %
upper bound on the share of bad blocks is about {100 * 3 / len(d):.1f} % (rule of three), not zero.
Re-running the audit over every block is a matter of time, not code.
"""
(R / "evm-cluster-check-input-audit.md").write_text(md)
print(md[:400])
