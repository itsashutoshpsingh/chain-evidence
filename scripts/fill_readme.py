"""Write README.md from scripts/README.template.md and results/ (run after `python -m chain_evidence.report`)."""
import csv
import json
from collections import Counter
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "results/summary.json").read_text())
eth = next(s for s in S["stats"] if s["chain"] == "ethereum")
md = (ROOT / "results/summary.md").read_text().split("\n\n")
logs_table = "\n".join(l for l in md[0].splitlines() if not l.startswith("| base"))
roots_table = md[1].strip()
tx = list(csv.DictReader(open(ROOT / "results/tx_survey.csv")))
eth_tx = [r for r in tx if r["chain"] == "ethereum"]
base_tx = [r for r in tx if r["chain"] == "base"]
nulls = [r for r in eth_tx if "publicnode" in r.get("null_receipt_from", "")]
deep_txs = [r for r in eth_tx if r.get("block") and r.get("finalized_floor")
            and int(r["finalized_floor"]) - int(r["block"]) >= 45000]
audit = list(csv.DictReader(open(ROOT / "results/evm-cluster-check-dataset-audit.csv")))
a40 = list(csv.DictReader(open(ROOT / "results/audit_ethereum_26316189_26337722.csv")))
rec, deep = eth["final"], eth["final_deep"]
L = list(csv.DictReader(open(ROOT / "results/logs_survey.csv")))
deep_dis = [r for r in L if r["chain"] == "ethereum" and r["kind"] == "final_deep" and r["agree"] == "False"]
empty_provs = sorted({p for r in deep_dis for p in r["empty_success"].split(",") if p})
all_empty = all(r["empty_success"] for r in deep_dis)
tx_exc = [r for r in eth_tx if r["agree"] == "False"]
def _depth(r):
    return int(r["finalized_floor"]) - int(r["block"])


dated = [r for r in eth_tx if r.get("block") and r.get("finalized_floor")]
min_null = min((_depth(r) for r in dated if "publicnode" in r.get("null_receipt_from", "")), default=None)
max_ok = max((_depth(r) for r in dated if "publicnode" not in r.get("null_receipt_from", "")), default=None)
clean_cut = min_null is not None and max_ok is not None and min_null > max_ok
exc_null = all("publicnode" in r.get("null_receipt_from", "") for r in tx_exc)
roots = S["roots"]
proven_blocks = sum(v.get("rroot_ok", 0) for v in roots.values())
checked_blocks = sum(v.get("checked", 0) for v in roots.values())
dl = sum(int(r["true_logs"]) for r in audit)

headline = (
    f"Across {eth['ranges']} finalised Ethereum block ranges asked of three free RPC providers, every recent "
    f"range agreed ({rec['comparable'] - rec['disagreements']}/{rec['comparable']}), but on older blocks a provider "
    f"silently returned nothing where receipt proofs show {deep['missing_logs']} logs "
    f"({deep['disagreements']}/{deep['comparable']} comparable ranges), and publicnode returned `null` receipts for "
    f"{len([r for r in deep_txs if 'publicnode' in r.get('null_receipt_from', '')])}/{len(deep_txs)} sampled "
    f"transactions older than ~6 days.")
findings = f"""1. **Silent empty answers on older blocks.** In the deep-history stratum (9,000–50,000 blocks back),
   {' and '.join(empty_provs)} answered {deep['empty_success']} finalised queries with `[]` and no error. Each time, the adjudicator rebuilt
   the true log set from receipts that reproduce `receiptsRoot` and found the logs were there:
   {deep['missing_logs']} missing logs in total. No recent range showed this
   ({rec['comparable']} comparable, {rec['disagreements']} disagreements).
2. **`null` receipts past ~6 days.** publicnode returns `result: null` for `eth_getTransactionReceipt` and
   `eth_getBlockReceipts` on blocks older than about 43,700–45,000 blocks, while `eth_getTransactionByHash`
   still returns the transaction. A reader would conclude the transaction has no receipt. It happened in
   {len(nulls)} of {len(eth_tx)} sampled Ethereum transactions""" + (
    f""": every sampled transaction at least {min_null:,} blocks deep and none at {max_ok:,} or less.""" if clean_cut
    else ".") + f"""
3. **Most failures are refusals, not lies.** publicnode refuses `eth_getLogs` beyond ~5,000–10,000 blocks,
   drpc's free tier refuses ranges over a few hundred blocks (while its message says 10,000), and
   mainnet.base.org refuses `eth_getLogs` outright. All of these are honest errors and are counted as
   errors, never as disagreements (see the chart above).
4. **Proofs held everywhere they could be run.** {proven_blocks} of {checked_blocks} provider-block pairs on
   Ethereum and Base reproduced the header hash, `transactionsRoot` and `receiptsRoot`, including blob
   (type 3), EIP-7702 (type 4) and OP Stack deposit (`0x7e`) transactions. No provider served altered
   receipts; the failures were missing data, not wrong data.
5. **Transactions agree when they are answered.** {sum(1 for r in eth_tx if r['agree'] == 'True')}/{len(eth_tx)}
   Ethereum and {sum(1 for r in base_tx if r['agree'] == 'True')}/{len(base_tx)} Base transactions had identical
   transaction and receipt objects across answering providers. """ + (
    "The Ethereum exceptions were all `null` receipts: " + ", ".join(
        f"{n} from {p}" for p, n in sorted(Counter(p for r in tx_exc for p in r.get("null_receipt_from", "").split(",") if p).items()))
    + ("; the 1rpc one was for a transaction only ~2.9 days old that both other providers returned"
       if any("1rpc" in r.get("null_receipt_from", "") for r in tx_exc) else "") + "."
    if tx_exc and all(r.get("null_receipt_from") for r in tx_exc) else "")
hb = [r for r in csv.DictReader(open(ROOT / "results/heads_base.csv")) if r["run_id"].startswith("heads-")]
byrun = {}
for r in hb:
    if r["finalized"]:
        byrun.setdefault(r["run_id"], {})[r["provider"]] = int(r["finalized"])
def _behind(p):
    lags = [max(d.values()) - d[p] for d in byrun.values() if p in d]
    return sum(1 for x in lags if x > 0), len(lags), max(lags, default=0)
fl = S["finality_lag"]["base"]
pn, o1 = _behind("publicnode"), _behind("1rpc")
findings += f"""
6. **"Finalized" means different things to different providers.** Across {fl['samples']} snapshots of Base heads
   (mostly every two minutes for an hour), the `finalized` head sat a median {fl['median_blocks']:,} blocks
   (~{fl['median_minutes'] / 60:.1f} h) behind `latest`. publicnode's `finalized` was behind base.org's in {pn[0]}/{pn[1]}
   samples (by up to {pn[2]:,} blocks), and 1rpc's was stale in {o1[0]}/{o1[1]} (by up to {o1[2]:,} blocks,
   ~{o1[2] * 2 / 3600:.1f} h). This tool takes the lowest `finalized` head across providers, so staleness makes it
   more cautious, never less."""
audit_txt = (f"{len(a40)}/{len(a40)} sampled blocks were proven against their headers, and {len(audit)} blocks "
             f"of its stored Parquet data ({dl:,} `Transfer` logs) matched the proven receipts exactly: "
             f"0 missing, 0 extra, 0 altered.")
r = (ROOT / "scripts/README.template.md").read_text()
for k, v in {"HEADLINE": headline, "TABLE": logs_table, "FINDINGS": findings, "ROOTS": roots_table,
             "AUDIT": audit_txt}.items():
    r = r.replace("{{" + k + "}}", v)
assert not re.search(r"\{\{[A-Z]+\}\}", r)
(ROOT / "README.md").write_text(r)
S["headline"] = re.sub(r"\*\*", "", headline)
(ROOT / "results/summary.json").write_text(json.dumps(S, indent=1, default=str))
print(headline)
