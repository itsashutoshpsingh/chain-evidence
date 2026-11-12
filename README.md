# chain-evidence

**{{HEADLINE}}**

{{TABLE}}

![What each provider returned for the same question](docs/img/provider_outcomes.png)

On-chain evidence is read through RPC providers, not from the chain. `chain-evidence` asks several
independent providers the same question, records every answer in a hashed evidence bundle, and
settles any disagreement with proof: it recomputes the block's `receiptsRoot`, `transactionsRoot` and
block hash locally, so the true set of logs is known without trusting any provider.

## What I found

{{FINDINGS}}

<p align="center"><img src="docs/img/receipt_depth.png" width="90%" alt="publicnode returns null receipts for blocks older than about six days"></p>

### Proof, not majority vote

Two providers agreeing does not make an answer complete. Every block below was rebuilt from the
provider's own data and checked against the header the whole network agrees on.

{{ROOTS}}

<p align="center"><img src="docs/img/receipts_root_proofs.png" width="90%" alt="Header, transaction and receipt roots recomputed per provider"></p>

## How it works

```mermaid
flowchart LR
    Q["Question<br/>eth_getLogs / tx / block"] --> P1["Provider A"]
    Q --> P2["Provider B"]
    Q --> P3["Provider C"]
    P1 & P2 & P3 --> E{"error or<br/>answer?"}
    E -- "429, quota, refusal" --> R["recorded as error<br/>(never as data)"]
    E -- "answer" --> N["normalise + diff<br/>by blockHash, txHash, logIndex"]
    N --> F{"block<br/>finalised?"}
    F -- "no" --> H["near-head column<br/>(lag expected)"]
    F -- "yes, all agree" --> B["evidence bundle<br/>SHA-256 of every answer"]
    F -- "yes, disagree" --> V["proof: header → hash,<br/>txs → transactionsRoot,<br/>receipts → receiptsRoot"]
    V --> J["true log set:<br/>names the provider that is wrong"]
    J --> B
    B --> C["verify-bundle:<br/>any edit is detected"]
```

![Terminal demo](docs/img/demo.svg)

## Use it

```bash
git clone https://github.com/itsashutoshpsingh/chain-evidence && cd chain-evidence
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install -e .
pytest -q                                   # offline, recorded mainnet and Base blocks

chain-evidence heads                                         # latest / finalized per provider
chain-evidence check --tx 0x...  --out tx.json               # tx + receipt everywhere, proven against its block
chain-evidence logs --from N --to M --address 0x... --out logs.json
chain-evidence verify-receipts --block N                     # per provider: do its receipts reproduce the roots?
chain-evidence verify-bundle logs.json                       # detect any later edit
chain-evidence audit --from N --to M --sample 40             # prove a sample of a dataset's input blocks
chain-evidence --chain base heads                            # Base (OP Stack), deposit tx type 0x7e supported
```

Providers live in `providers.toml` (git-ignored; copy `providers.example.toml`). Keys go in
environment variables referenced as `${ALCHEMY_KEY}`. A provider whose key variable is unset is skipped,
never queried unauthenticated. Endpoints are stored in bundles with key-like path segments redacted.

### An evidence bundle

A real bundle from the survey (logs abbreviated). 1rpc returned an empty success. The proof says
there are 6 logs, and drpc's 6 are exactly those.

```json
{
 "schema": "chain-evidence/bundle/v1",
 "chain": "ethereum",
 "request": {"method": "eth_getLogs", "params": [{"fromBlock": "0x192095a", "toBlock": "0x192095a",
             "address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "topics": ["0xddf252ad…"]}]},
 "responses": [
  {"provider": "publicnode", "ok": false, "error": "-32602: Archive requests require a personal token…"},
  {"provider": "drpc", "ok": true, "result": "[6 logs]", "result_sha256": "cfcfee77…30cd4b02"},
  {"provider": "1rpc", "ok": true, "result": "[0 logs]", "result_sha256": "4f53cda1…1202b945"}
 ],
 "comparison": {"agree": false, "providers": {"drpc": {"count": 6, "missing": 0}, "1rpc": {"count": 0, "missing": 6}}},
 "finality": {"floor": 26394863, "range_final": true},
 "proofs": {"proven": true, "true_count": 6, "proof_sources": ["drpc"],
            "providers": {"drpc": {"missing": 0}, "1rpc": {"missing": 6}}},
 "bundle_sha256": "c8b48a68c059b64d1b4578b6e69c1dac6423c47f32b1343e0cf07e79d6b90c81"
}
```

Full file: [`results/bundles/ethereum/20261111T233144Z_0024.json`](results/bundles/ethereum/20261111T233144Z_0024.json).
CI re-verifies the hash of every published bundle on every push.

## Used by evm-cluster-check

[`evm-cluster-check`](https://github.com/itsashutoshpsingh/evm-cluster-check) measures false links made by
Ethereum address-clustering rules over 1–3 November 2026. Before its results were read, its inputs went
through this tool: {{AUDIT}} See [`results/evm-cluster-check-input-audit.md`](results/evm-cluster-check-input-audit.md).

## More charts

| | |
|---|---|
| ![Disagreement rate per run](docs/img/disagreement_rate.png) | ![Finalized tag lag](docs/img/finalized_lag.png) |

## Repository

```
src/chain_evidence/
  query.py      same request to every provider; paced; errors kept apart from answers
  compare.py    normalise + diff logs, headers, receipts
  finality.py   finalized head per provider; conservative floor
  proofs.py     RLP + Merkle-Patricia: receiptsRoot, transactionsRoot, block hash (types 0-4, 0x7e)
  checks.py     check / logs / verify-receipts / adjudication
  bundle.py     evidence bundle + tamper check
  survey.py     repeatable measurement runs -> results/*.csv
  report.py     tables, charts, results/summary.json
  cli.py        chain-evidence command
tests/          offline tests on recorded Ethereum and Base blocks
results/        survey CSVs, evidence bundles, input audit
docs/           method, reading notes, what went wrong, figures
```

## Read more

- [`docs/method.md`](docs/method.md): error classes, normalisation, finality rule, proof, survey design,
  measured provider policies
- [`docs/what-went-wrong.md`](docs/what-went-wrong.md): what I got wrong, including the evidence I deleted
- [`docs/reading-notes.md`](docs/reading-notes.md): EtherDiffer (FSE 2023), Envio "Nodes Silently Miss
  Events" (2026), the JSON-RPC spec, OP Stack finality, and issues found while searching for prior work

## Limits

- These are measurements of three free public endpoints in November 2026, not of providers' paid
  tiers and not of any analytics vendor. Endpoint behaviour changes; every number carries its date.
- 1rpc's free quota ran out during the study, and 1rpc relays at least one other provider's backend,
  so many comparisons had two answers, not three. Adding keyed providers to `providers.toml` and
  re-running `survey` is the obvious next step.
- A zero disagreement count bounds the rate; it does not prove it is zero. Intervals are 95 % Wilson.

MIT licence. Copyright (c) 2026 Ashutosh Pal Singh.
