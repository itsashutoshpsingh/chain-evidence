"""Check a stored Transfer-log dataset against logs taken from proven receipts.

Input: a JSON-lines export of the dataset's rows (block, tx_hash, log_index, address, topic0, a1, a2, data),
for example produced from evm-cluster-check's Parquet files with:

    python -c "import pandas as pd,glob,sys; blocks=set(map(int,sys.argv[1].split(',')));
               pd.concat(pd.read_parquet(f) for f in glob.glob('data/raw/eth/logs/*.parquet'))
                 .query('block in @blocks').to_json(sys.stdout, orient='records', lines=True)" <blocks>

Usage: python scripts/audit_evm_dataset.py export.jsonl results/evm-cluster-check-dataset-audit.csv
"""
import csv
import json
import sys
from collections import defaultdict

from chain_evidence import checks, providers

ZERO_TOPIC = "0x" + "0" * 24


def norm_proven(l):
    t = [x.lower() for x in l["topics"]]
    return {"address": l["address"].lower(), "a1": ("0x" + t[1][-40:]) if len(t) > 1 else "",
            "a2": ("0x" + t[2][-40:]) if len(t) > 2 else "", "data": l["data"].lower()[:2 + 64 * 3]}


def main(export, out):
    stored = defaultdict(dict)
    for line in open(export):
        r = json.loads(line)
        if r["topic0"].lower() == checks.TRANSFER:
            stored[r["block"]][(r["tx_hash"].lower(), r["log_index"])] = {
                "address": r["address"].lower(), "a1": r["a1"].lower(), "a2": r["a2"].lower(),
                "data": r["data"].lower()}
    ps = providers.load("ethereum")
    rows = []
    for block in sorted(stored):
        pb = checks.proven_block(ps, block)
        if pb["verify"] is None:
            rows.append({"block": block, "proven": False})
            continue
        truth = {(l["transactionHash"].lower(), int(l["logIndex"], 16)): norm_proven(l)
                 for r in pb["receipts"] for l in r["logs"] if l["topics"] and l["topics"][0].lower() == checks.TRANSFER}
        s = stored[block]
        rows.append({"block": block, "proven": True, "proof_source": pb["verify"]["source"],
                     "true_logs": len(truth), "stored_logs": len(s),
                     "missing_from_dataset": len(set(truth) - set(s)), "extra_in_dataset": len(set(s) - set(truth)),
                     "field_mismatch": sum(1 for k in set(truth) & set(s) if truth[k] != s[k])})
        print(rows[-1])
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)), restval="")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(*sys.argv[1:3])
