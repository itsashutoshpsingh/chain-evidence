"""chain-evidence command line."""
import argparse
import json
import sys

from . import bundle, checks, finality, providers, survey


def _out(b, path):
    text = json.dumps(b, indent=1)
    if path:
        open(path, "w").write(text)
        print(f"bundle written: {path}  sha256={b['bundle_sha256']}", file=sys.stderr)
    return b


def _summary(b):
    c = b["comparison"]
    print(json.dumps({"agree": c.get("agree"), "errors": c.get("errors"),
                      "providers": {p: {k: v for k, v in d.items() if k != "missing_keys"}
                                    for p, d in c.get("providers", {}).items()},
                      "finality": {k: v for k, v in (b.get("finality") or {}).items() if k != "heads"},
                      "proofs": b.get("proofs"), "bundle_sha256": b["bundle_sha256"]}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chain-evidence", description=__doc__)
    ap.add_argument("--chain", default="ethereum")
    ap.add_argument("--providers", help="path to providers.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check", help="compare one transaction across providers and prove its receipt")
    s.add_argument("--tx", required=True)
    s.add_argument("--out")
    s = sub.add_parser("logs", help="compare eth_getLogs for a block range")
    s.add_argument("--from", dest="frm", type=int, required=True)
    s.add_argument("--to", type=int, required=True)
    s.add_argument("--address")
    s.add_argument("--topic0")
    s.add_argument("--out")
    s = sub.add_parser("verify-receipts", help="prove a block's receipts against its header, per provider")
    s.add_argument("--block", type=int, required=True)
    s = sub.add_parser("verify-bundle", help="detect any change to a saved evidence bundle")
    s.add_argument("path")
    sub.add_parser("heads", help="latest and finalized block per provider")
    s = sub.add_parser("survey", help="measurement run; appends to results/*.csv")
    s.add_argument("--ranges", type=int, default=200)
    s.add_argument("--near-head", type=int, default=30)
    s.add_argument("--tx-sample", type=int, default=0)
    s.add_argument("--root-sample", type=int, default=0)
    s.add_argument("--seed", type=int)
    s = sub.add_parser("audit", help="prove a sample of blocks from a dataset's window and check each provider")
    s.add_argument("--from", dest="frm", type=int, required=True)
    s.add_argument("--to", type=int, required=True)
    s.add_argument("--sample", type=int, default=40)
    s.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    if a.cmd == "verify-bundle":
        problems = bundle.verify(json.load(open(a.path)))
        print("OK: bundle intact" if not problems else "TAMPERED:\n  " + "\n  ".join(problems))
        return 0 if not problems else 1
    ps = providers.load(a.chain, a.providers)
    if len(ps) < 2:
        ap.error(f"need at least 2 providers for chain {a.chain}, found {len(ps)}")
    if a.cmd == "heads":
        print(json.dumps(finality.heads(ps), indent=1))
    elif a.cmd == "check":
        b = _out(checks.tx(ps, a.chain, a.tx), a.out)
        _summary(b)
        return 0 if b["comparison"]["agree"] else 2
    elif a.cmd == "logs":
        b = _out(checks.logs(ps, a.chain, a.frm, a.to, a.address, a.topic0), a.out)
        _summary(b)
        return 0 if b["comparison"]["agree"] else 2
    elif a.cmd == "verify-receipts":
        rows = checks.verify_receipts(ps, a.block)
        print(json.dumps(rows, indent=1))
        return 0 if all(r.get("receipts_root_ok") for r in rows if "error" not in r) else 2
    elif a.cmd == "survey":
        if a.ranges or a.near_head:
            survey.logs_survey(ps, a.chain, a.ranges, a.near_head, a.seed)
        if a.tx_sample:
            survey.tx_survey(ps, a.chain, a.tx_sample, a.seed)
        if a.root_sample:
            survey.root_survey(ps, a.chain, a.root_sample, a.seed)
    elif a.cmd == "audit":
        survey.block_audit(ps, a.chain, a.frm, a.to, a.sample, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
