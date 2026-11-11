"""Repeatable measurement runs. Every run appends to results/*.csv with a run id."""
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from . import checks, finality
from .providers import ROOT

RESULTS = ROOT / "results"
TOKENS = {
    "ethereum": ["0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
                 "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
                 "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
                 "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
                 "0x514910771af9ca656af840dff83e8264ecf986ca",  # LINK
                 "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"],  # Uniswap v3 USDC/WETH 0.05%
    "base": ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
             "0x4200000000000000000000000000000000000006",  # WETH
             "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",  # USDbC
             "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"],  # DAI
}
LOOKBACK = {"ethereum": 50_000, "base": 300_000}  # about 7 days on each chain
# Window every provider serves for eth_getLogs (publicnode refuses older without a token).
RECENT = {"ethereum": 4_500, "base": 20_000}


def _append(name, rows):
    """Append rows; if the columns changed since the file was created, rewrite it with the union."""
    if not rows:
        return
    path = RESULTS / name
    keys = list(rows[0].keys())
    old = list(csv.DictReader(open(path))) if path.exists() else []
    if old and list(old[0].keys()) != keys:
        keys = list(dict.fromkeys(list(old[0].keys()) + keys))
        rows, mode = old + rows, "w"
    else:
        mode = "a"
    with open(path, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval="")
        if mode == "w" or not old:
            w.writeheader()
        w.writerows(rows)


def _save_bundle(chain, run_id, i, b):
    d = RESULTS / "bundles" / chain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{run_id}_{i:04d}.json"
    p.write_text(json.dumps(b, indent=1))
    return str(p.relative_to(ROOT))


def _row(run_id, chain, kind, shape, frm, to, addr, topic0, b, header=None):
    c = b["comparison"]
    per = c.get("providers", {})
    return {
        "run_id": run_id, "chain": chain, "kind": kind, "shape": shape, "from_block": frm, "to_block": to,
        "address": addr or "", "topic0": "transfer" if topic0 else "",
        "providers_ok": sum(1 for r in b["responses"] if r["ok"]), "errors": json.dumps(c.get("errors", {})),
        "agree": c.get("agree"), "union": c.get("union"),
        "empty_success": ",".join(p for p, v in per.items() if v["count"] == 0 and (c.get("union") or 0) > 0),
        "per_provider": json.dumps({p: [v["count"], v["missing"], v["content_mismatch"]] for p, v in per.items()}),
        "range_final": b["finality"]["range_final"], "finalized_floor": b["finality"]["floor"],
        "header_agree": None if header is None else header["comparison"].get("agree"),
        "header_diff_fields": "" if header is None else ",".join(header["comparison"].get("fields", [])),
        "adjudication": json.dumps(b.get("proofs")) if b.get("proofs") else "",
        "bundle_sha256": b["bundle_sha256"], "bundle": "",
    }


def logs_survey(providers, chain, n_final=200, n_head=30, seed=None, keep_agree=2, log=print):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rng = random.Random(seed if seed is not None else run_id)
    heads = finality.heads(providers)
    _append(f"heads_{chain}.csv", [{"run_id": run_id, "provider": p, **v} for p, v in heads.items()])
    floor = finality.finalized_floor(heads)
    rows, kept = [], 0
    plan = []
    for _ in range(n_final):
        deep = rng.random() < 0.25
        lo, hi = ((floor - LOOKBACK[chain], floor - 2 * RECENT[chain]) if deep else (floor - RECENT[chain], floor - 64))
        start = rng.randint(lo, hi)
        kind = "final_deep" if deep else "final"
        if rng.random() < 0.3:
            plan.append((kind, "block", start, start, None, None))
        else:
            size = rng.choice([1, 10, 25])  # 25 = smallest cap seen (1rpc backends)
            plan.append((kind, f"token{size}", start, start + size - 1, rng.choice(TOKENS[chain]),
                         checks.TRANSFER if rng.random() < 0.5 else None))
    for _ in range(n_head):
        plan.append(("near_head", rng.choice(["block", "token1"]), None, None, None, None))
    for i, (kind, shape, frm, to, addr, topic0) in enumerate(plan):
        h = heads
        if kind == "near_head":
            h = finality.heads(providers)
            tip = max(v["latest"] for v in h.values() if v.get("latest"))
            frm = to = tip - rng.randint(0, 2)
            if shape == "token1":
                addr = rng.choice(TOKENS[chain])
        b = checks.logs(providers, chain, frm, to, addr, topic0, heads=h)
        hdr = checks.block_headers(providers, chain, frm) if shape == "block" else None
        row = _row(run_id, chain, kind, shape, frm, to, addr, topic0, b, hdr)
        if row["agree"] is False or (hdr and hdr["comparison"].get("agree") is False) or kept < keep_agree:
            if row["agree"]:
                kept += 1
            row["bundle"] = _save_bundle(chain, run_id, i, b)
            if hdr and hdr["comparison"].get("agree") is False:
                _save_bundle(chain, run_id + "_hdr", i, hdr)
        rows.append(row)
        _append("logs_survey.csv", [row])  # per row, so an interrupted run keeps its data
        log(f"[{i + 1}/{len(plan)}] {chain} {kind} {shape} {frm}-{to} agree={row['agree']} "
            f"ok={row['providers_ok']} hdr={row['header_agree']}")
    return run_id, rows


def tx_survey(providers, chain, n=50, seed=None, log=print):
    """Sample transactions from recent finalised blocks and compare tx + receipt everywhere."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rng = random.Random(seed if seed is not None else run_id)
    heads = finality.heads(providers)
    floor = finality.finalized_floor(heads)
    rows = []
    p0 = providers[0]
    from .query import call
    while len(rows) < n:
        blk = call(p0, "eth_getBlockByNumber", [hex(rng.randint(floor - LOOKBACK[chain], floor - 64)), False])
        if not (blk.ok and blk.result and blk.result["transactions"]):
            continue
        h = rng.choice(blk.result["transactions"])
        b = checks.tx(providers, chain, h, prove=len(rows) < 10)  # full proof on the first 10 only
        c = b["comparison"]
        row = {"run_id": run_id, "chain": chain, "tx": h, "agree": c["agree"],
               "block": int(blk.result["number"], 16), "finalized_floor": floor,
               "null_receipt_from": ",".join(c["receipt"].get("null_from", [])),
               "receipt_diff": ",".join(c["receipt"].get("fields", [])),
               "tx_diff": ",".join(c["transaction"].get("fields", [])),
               "errors": json.dumps(c["errors"]),
               "proof": json.dumps(b["proofs"]) if b["proofs"] else "",
               "bundle_sha256": b["bundle_sha256"], "bundle": ""}
        if c["agree"] is False:
            row["bundle"] = _save_bundle(chain, run_id + "_tx", len(rows), b)
        rows.append(row)
        log(f"[tx {len(rows)}/{n}] {chain} agree={row['agree']} {row['receipt_diff']} {row['tx_diff']}")
    _append("tx_survey.csv", rows)
    return run_id, rows


def root_survey(providers, chain, n=20, seed=None, per_tx_max=80, log=print):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rng = random.Random(seed if seed is not None else run_id)
    floor = finality.finalized_floor(finality.heads(providers))
    rows = []
    for i in range(n):
        number = rng.randint(floor - LOOKBACK[chain], floor - 64)
        for r in checks.verify_receipts(providers, number, per_tx_max=per_tx_max):
            r = {"run_id": run_id, "chain": chain, **r}
            rows.append(r)
            log(f"[root {i + 1}/{n}] {chain} {r['provider']} {number} hdr={r.get('header_hash_ok')} "
                f"txroot={r.get('transactions_root_ok')} rroot={r.get('receipts_root_ok')} "
                f"getLogs_missing={r.get('getlogs_missing')} err={r.get('error', '')[:60]}")
    keys = ["run_id", "chain", "provider", "block", "hash", "number", "receipts_method", "receipts_n",
            "header_hash_ok", "transactions_root_ok", "receipts_root_ok", "receipts_block_hash_ok",
            "getlogs_missing", "getlogs_mismatch", "getlogs_extra", "getlogs_error", "receipts_null", "error"]
    _append("root_survey.csv", [{k: r.get(k, "") for k in keys} for r in rows])
    return run_id, rows


def block_audit(providers, chain, frm, to, n=40, seed=0, log=print):
    """Audit a dataset's input window: prove sampled blocks, then compare each provider's
    single-block eth_getLogs (Transfer topic) with the Transfer logs in the proven receipts."""
    from . import compare
    from .query import call
    rng = random.Random(seed)
    blocks = sorted(rng.sample(range(frm, to + 1), n))
    rows = []
    for i, number in enumerate(blocks):
        pb = checks.proven_block(providers, number)
        row = {"chain": chain, "block": number, "proven": pb["verify"] is not None,
               "proof_source": pb["verify"]["source"] if pb["verify"] else "",
               "hash_consensus": pb["verify"]["hash_consensus"] if pb["verify"] else ""}
        truth = [l for r in (pb["receipts"] or []) for l in r["logs"]
                 if l["topics"] and l["topics"][0].lower() == checks.TRANSFER]
        row["true_transfer_logs"] = len(truth) if pb["verify"] else ""
        for p in providers:
            a = call(p, "eth_getLogs", [{"fromBlock": hex(number), "toBlock": hex(number), "topics": [checks.TRANSFER]}])
            if not a.ok:
                row[f"{p.name}"] = "error: " + (a.error or "")[:80]
            elif pb["verify"]:
                c = compare.compare_logs({"truth": truth, p.name: a.result})["providers"][p.name]
                row[f"{p.name}"] = "ok" if (c["missing"] == 0 and c["content_mismatch"] == 0 and
                                            len(a.result) == len(truth)) else \
                    f"DIFF missing={c['missing']} mismatch={c['content_mismatch']} n={len(a.result)}"
            else:
                row[f"{p.name}"] = f"unproven n={len(a.result)}"
        rows.append(row)
        log(f"[audit {i + 1}/{n}] {number} proven={row['proven']} " +
            " ".join(f"{p.name}={row[p.name][:30]}" for p in providers))
    _append(f"audit_{chain}_{frm}_{to}.csv", rows)
    return rows
