"""The checks behind every CLI command: ask all providers, compare, prove, bundle."""
from . import bundle, compare, finality, proofs
from .query import call, call_all

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _ok(answers):
    return {p: a.result for p, a in answers.items() if a.ok}


def _errors(answers):
    return {p: a.error for p, a in answers.items() if not a.ok}


def proven_block(providers, number: int) -> dict:
    """Fetch block + receipts from the first provider able to give a self-consistent set.

    The result is trusted only if the header hashes to the block hash that *all*
    providers report, and the receipts reproduce the header's receiptsRoot.
    """
    hashes = {p: (a.result or {}).get("hash") for p, a in
              call_all(providers, "eth_getBlockByNumber", [hex(number), False]).items() if a.ok}
    consensus = set(hashes.values())
    for p in providers:
        b = call(p, "eth_getBlockByNumber", [hex(number), True])
        r = call(p, "eth_getBlockReceipts", [hex(number)])
        if not (b.ok and r.ok and b.result and r.result is not None):
            continue
        v = proofs.verify_block(b.result, r.result)
        v["source"] = p.name
        v["hash_consensus"] = len(consensus) == 1 and b.result["hash"] in consensus
        if v["header_hash_ok"] and v["receipts_root_ok"]:
            return {"verify": v, "block": b.result, "receipts": r.result}
    return {"verify": None, "block": None, "receipts": None}


def _match(log, address, topic0):
    if address and log["address"].lower() not in {a.lower() for a in (address if isinstance(address, list) else [address])}:
        return False
    return not topic0 or (log["topics"] and log["topics"][0].lower() == topic0.lower())


def adjudicate_logs(providers, frm: int, to: int, address=None, topic0=None, answers=None) -> dict:
    """Rebuild the true log set for a range from proven receipts; say which provider deviates."""
    truth, sources = [], []
    for n in range(frm, to + 1):
        pb = proven_block(providers, n)
        if pb["verify"] is None:
            return {"proven": False, "reason": f"no provider gave verifiable receipts for block {n}"}
        sources.append(pb["verify"]["source"])
        truth += [l for r in pb["receipts"] for l in r["logs"] if _match(l, address, topic0)]
    out = {"proven": True, "true_count": len(truth), "proof_sources": sorted(set(sources)), "providers": {}}
    for p, logs in (answers or {}).items():
        c = compare.compare_logs({"truth": truth, p: logs})["providers"][p]
        extra = len({compare.log_key(l) for l in compare.norm_logs(logs)} -
                    {compare.log_key(l) for l in compare.norm_logs(truth)})
        out["providers"][p] = {"missing": c["missing"], "content_mismatch": c["content_mismatch"], "extra": extra}
    return out


def logs(providers, chain, frm, to, address=None, topic0=None, heads=None, adjudicate=True) -> dict:
    flt = {"fromBlock": hex(frm), "toBlock": hex(to)}
    if address:
        flt["address"] = address
    if topic0:
        flt["topics"] = [topic0]
    answers = call_all(providers, "eth_getLogs", [flt])
    ok = _ok(answers)
    cmp = compare.compare_logs(ok) if len(ok) >= 2 else {"agree": None, "union": None, "providers": {}}
    cmp["errors"] = _errors(answers)
    heads = heads if heads is not None else finality.heads(providers)
    fin = {"heads": heads, "floor": finality.finalized_floor(heads), "range_final": finality.is_final(to, heads)}
    proof = None
    if adjudicate and cmp["agree"] is False and fin["range_final"]:
        proof = adjudicate_logs(providers, frm, to, address, topic0, ok)
    b = bundle.make(chain, {"method": "eth_getLogs", "params": [flt]}, answers, providers, cmp, fin, proof)
    return b


def block_headers(providers, chain, number) -> dict:
    answers = call_all(providers, "eth_getBlockByNumber", [hex(number), False])
    ok = _ok(answers)
    cmp = compare.compare_blocks(ok) if len(ok) >= 2 else {"agree": None}
    cmp["errors"] = _errors(answers)
    return bundle.make(chain, {"method": "eth_getBlockByNumber", "params": [hex(number), False]},
                       answers, providers, cmp)


def tx(providers, chain, txhash, prove=True) -> dict:
    rec = call_all(providers, "eth_getTransactionReceipt", [txhash])
    txs = call_all(providers, "eth_getTransactionByHash", [txhash])
    ok_r, ok_t = _ok(rec), _ok(txs)
    cmp = {"receipt": compare.compare_receipts(ok_r) if len(ok_r) >= 2 else {"agree": None},
           "transaction": compare.compare_receipts({p: dict(t, logs=[]) for p, t in ok_t.items() if t})
           if len(ok_t) >= 2 else {"agree": None},
           "errors": {**{f"receipt:{k}": v for k, v in _errors(rec).items()},
                      **{f"tx:{k}": v for k, v in _errors(txs).items()}}}
    cmp["agree"] = cmp["receipt"].get("agree") is not False and cmp["transaction"].get("agree") is not False
    heads = finality.heads(providers)
    some = next((r for r in ok_r.values() if r), None)
    fin = None
    proof = None
    if some:
        n = int(some["blockNumber"], 16)
        fin = {"heads": heads, "floor": finality.finalized_floor(heads), "block": n,
               "block_final": finality.is_final(n, heads)}
        if prove:
            pb = proven_block(providers, n)
            if pb["verify"]:
                truth = next(r for r in pb["receipts"] if r["transactionHash"].lower() == txhash.lower())
                proof = {"block_verification": pb["verify"],
                         "providers_match_proven_receipt": {
                             p: compare.compare_receipts({"truth": truth, p: r})["agree"] for p, r in ok_r.items()}}
            else:
                proof = {"block_verification": None}
    answers = {f"receipt:{k}": v for k, v in rec.items()} | {f"tx:{k}": v for k, v in txs.items()}
    return bundle.make(chain, {"method": "tx-check", "params": [txhash]}, answers, providers, cmp, fin, proof)


def verify_receipts(providers, number: int, per_tx_max: int = 80) -> list[dict]:
    """Per provider: do its block + receipts reproduce the header roots? Do its getLogs match?"""
    out = []
    for p in providers:
        row = {"provider": p.name, "block": number}
        b = call(p, "eth_getBlockByNumber", [hex(number), True])
        r = call(p, "eth_getBlockReceipts", [hex(number)])
        receipts = r.result if r.ok else None
        row["receipts_method"] = "eth_getBlockReceipts" if r.ok else None
        if r.ok and r.result is None and b.ok and b.result and b.result["transactions"]:
            # success with no data: the most dangerous answer, because it looks like "no receipts"
            row["receipts_null"] = True
            row["error"] = "null result for eth_getBlockReceipts (success, no data)"
        if not r.ok and b.ok and b.result and len(b.result["transactions"]) > per_tx_max:
            row["error"] = (f"skipped: no eth_getBlockReceipts and {len(b.result['transactions'])} txs "
                            f"> per-tx limit {per_tx_max}")
        elif not r.ok and b.ok and b.result:
            # fallback for providers without eth_getBlockReceipts: one call per transaction
            got = [call(p, "eth_getTransactionReceipt", [t["hash"]]) for t in b.result["transactions"]]
            if all(g.ok and g.result for g in got):
                receipts, row["receipts_method"] = [g.result for g in got], "per-tx eth_getTransactionReceipt"
            else:
                row["error"] = f"receipts unavailable: {r.error}"
        if not (b.ok and b.result):
            row["error"] = f"block unavailable: {b.error}"
            out.append(row)
            continue
        row.update(proofs.verify_block(b.result, receipts))
        lg = call(p, "eth_getLogs", [{"fromBlock": hex(number), "toBlock": hex(number)}])
        if lg.ok and receipts is not None:
            truth = [l for x in receipts for l in x["logs"]]
            c = compare.compare_logs({"truth": truth, p.name: lg.result})["providers"][p.name]
            row["getlogs_missing"], row["getlogs_mismatch"] = c["missing"], c["content_mismatch"]
            row["getlogs_extra"] = len(lg.result) - (len(truth) - c["missing"])
        else:
            row["getlogs_error"] = lg.error
        out.append(row)
    return out
