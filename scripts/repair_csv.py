"""One-off repair: a results CSV that received rows from two code versions with different columns.

Rows are matched to a layout by field count; the file is rewritten with the union of columns.
Usage: python scripts/repair_csv.py results/tx_survey.csv
"""
import csv
import sys

LAYOUTS = {
    "tx_survey.csv": [
        ["run_id", "chain", "tx", "agree", "receipt_diff", "tx_diff", "errors", "proof", "bundle_sha256", "bundle"],
        ["run_id", "chain", "tx", "agree", "block", "finalized_floor", "null_receipt_from", "receipt_diff",
         "tx_diff", "errors", "proof", "bundle_sha256", "bundle"],
    ],
}


def main(path):
    layouts = {len(l): l for l in LAYOUTS[path.rsplit("/", 1)[-1]]}
    raw = list(csv.reader(open(path)))
    body = [r for r in raw[1:] if r != raw[0]]
    rows = [dict(zip(layouts[len(r)], r)) for r in body]
    keys = list(dict.fromkeys(k for l in layouts.values() for k in l))
    keys = layouts[max(layouts)] + [k for k in keys if k not in layouts[max(layouts)]]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval="")
        w.writeheader()
        w.writerows(rows)
    print(f"{path}: {len(rows)} rows rewritten with {len(keys)} columns")


if __name__ == "__main__":
    main(sys.argv[1])
