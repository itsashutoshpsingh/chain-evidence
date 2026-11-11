# Reading notes

## 1. EtherDiffer — Kim & Hwang, "Differential Testing on RPC Services of Ethereum Nodes", ESEC/FSE 2023 (doi:10.1145/3611643.3616251)

**What they did.** Built a differential tester for the JSON-RPC layer of four execution clients. It first
creates a *non-deterministic* private chain (concurrent transactions, propagation delay, so forks and
reorgs actually happen), then generates test cases two ways: property-based generation of valid calls
and type-preserving mutation into "semantically invalid yet executable" calls. Every case runs on every
node; any difference in return value or error handling is a deviation.

**Numbers.** Generation success ratios of 98.8 % (valid) and 95.4 % (invalid). 48 classes of deviation,
11 of them implementation bugs (crashes, denial of service). 44 classes reported; acknowledgements and
patches received.

**Root causes they name.** The spec is silent on (1) how non-deterministic events such as reorgs should
be handled and (2) what to do with invalid arguments. So two correct nodes can disagree.

**What I take from it.**
- Differences between providers are expected and are *not automatically bugs*. Classify before
  claiming.
- Their target is clients on a private chain; mine is the providers an investigator actually uses, on
  mainnet, where I cannot control the chain. So I compare answers *and* check them against the block's
  own commitments.
- Error handling is part of the answer: a refusal and an empty success mean very different things to a
  downstream tracing tool. I record both, separately.

## 2. Envio, "Nodes Silently Miss Events" (blog, published 7 September 2026)

**Claim.** `eth_getLogs` and `eth_getBlockReceipts` responses carry nothing that shows whether they are
complete. A node with a damaged receipt/log index usually returns *fewer logs*, not an error.

**Evidence collected.** A trail of issues across clients and years: go-ethereum #18198 (2018), Besu #1153
(2020), Erigon #16613 and Nethermind #9178 (August 2025, empty `eth_getLogs` for historical Gnosis
blocks that other providers served), HOPR #7437 (September 2025). Hive's RPC compatibility suite had
about 4 of ~190 tests covering `eth_getLogs`, roughly half failing for months. A 50-block, block-by-block
script against the public Gnosis endpoint found it inconsistent roughly 1 time in 50.

**Their fix.** Recompute `transactionsRoot` and `receiptsRoot` from complete block data and compare with
the header, plus structural checks (parent hash chain, contiguous indices, cumulative gas).

**What I take from it.**
- Comparison between providers finds disagreement; only the receipts-root proof says *who is right*.
  I implement both and use the proof to adjudicate every disagreement on finalised blocks.
- The 1-in-50 figure is from one public endpoint on Gnosis over 50 blocks; it is a hint, not a rate.
  My job is to measure, on Ethereum and Base, with intervals.

## 3. Ethereum execution JSON-RPC specification (ethereum.github.io/execution-apis)

- `eth_getLogs(filter)`: `fromBlock`/`toBlock`/`address`/`topics` or `blockHash`. The spec puts no
  limit on range or result size; every provider adds its own (see `method.md`, "provider policies").
- `eth_getBlockByNumber(tag, full)`: tags `latest`, `safe`, `finalized`, `earliest`, `pending`.
  `finalized` is the most recent block finalised by the consensus layer; it cannot be reorged without
  slashing a third of stake.
- `eth_getTransactionReceipt(hash)` / `eth_getBlockReceipts(block)`: receipts include `logs`,
  `logsBloom`, `cumulativeGasUsed`, `status` and typed-envelope `type`. Receipts are not in the block;
  the header commits to them via `receiptsRoot` (a Merkle-Patricia trie keyed by RLP(index), values
  are EIP-2718 typed receipts).
- The block hash is keccak256 of the RLP header. Header fields grow with forks (London baseFee,
  Shanghai withdrawalsRoot, Cancun blob fields and parentBeaconBlockRoot, Prague requestsHash). My
  encoder stops at the first field the block does not have, and is tested on real blocks.

## 4. OP Stack (Base) specs and docs — finality and deposits

- Three heads: *unsafe* (sequencer gossip), *safe* (batch data posted on L1), *finalized* (that L1
  block finalised; typically ~15–30 min). Only `finalized` is reorg-proof. So I apply the same rule as
  on Ethereum: compare only finalised Base blocks, report the rest separately.
- Deposit transactions (type `0x7e`) are derived from L1 and have no signature; their receipts add
  `depositNonce` (Regolith) and `depositReceiptVersion` (Canyon) to the RLP. Base receipts also carry
  L1-fee fields (`l1Fee`, `l1GasUsed`, …) that are *not* consensus data; differences there would be
  presentation, not evidence.

## Search before claiming

I searched GitHub and the web for existing cross-provider log-completeness measurements on Ethereum
mainnet. I found the client-level work above and indexer write-ups, but no published per-provider
disagreement rate with intervals. That does not mean none exists; the README does not claim "first".
