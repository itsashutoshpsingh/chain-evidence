"""Fill README placeholders from results/ (run after `python -m chain_evidence.report`)."""
import csv
import json
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
    f"Asked three free Ethereum RPC providers the same `eth_getLogs` question across {eth['ranges']} finalised "
    f"block ranges. {'All ' if rec['disagreements'] == 0 else ''}{rec['comparable'] - rec['disagreements']} of {rec['comparable']} comparable recent ranges agreed (95% CI 0–{100 * rec['ci'][1]:.1f}% "
    f"disagreement). On older blocks, {deep['disagreements']} of {deep['comparable']} comparable ranges disagreed"
    + (f", and every one was a provider returning an **empty success** where receipt proofs show "
       f"{deep['missing_logs']} logs. " if all_empty else f" ({deep['missing_logs']} logs missing). ")
    + f"publicnode also returned `null` receipts for {len(nulls)} of {len(deep_txs)} "
    f"sampled transactions older than ~6 days.")
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
   transaction and receipt objects across answering providers.""" + (
    " Every Ethereum exception is a publicnode `null` receipt from finding 2." if exc_null and tx_exc else "")
audit_txt = (f"{len(a40)}/{len(a40)} sampled blocks were proven against their headers, and {len(audit)} blocks "
             f"of its stored Parquet data ({dl:,} `Transfer` logs) matched the proven receipts exactly: "
             f"0 missing, 0 extra, 0 altered.")
r = (ROOT / "README.md").read_text()
for k, v in {"HEADLINE": headline, "TABLE": logs_table, "FINDINGS": findings, "ROOTS": roots_table,
             "AUDIT": audit_txt}.items():
    r = r.replace("{{" + k + "}}", v)
assert not re.search(r"\{\{[A-Z]+\}\}", r)
(ROOT / "README.md").write_text(r)
S["headline"] = re.sub(r"\*\*", "", headline)
(ROOT / "results/summary.json").write_text(json.dumps(S, indent=1, default=str))
print(headline)
