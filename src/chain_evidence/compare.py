"""Normalise provider answers and report exactly how they differ."""

LOG_FIELDS = ("address", "topics", "data", "blockNumber", "blockHash",
              "transactionHash", "transactionIndex", "logIndex", "removed")


def _h(x):
    return x.lower() if isinstance(x, str) else x


def _int(x):
    return int(x, 16) if isinstance(x, str) else x


def norm_log(log: dict) -> dict:
    return {
        "address": _h(log.get("address")),
        "topics": [_h(t) for t in log.get("topics", [])],
        "data": _h(log.get("data")),
        "blockNumber": _int(log.get("blockNumber")),
        "blockHash": _h(log.get("blockHash")),
        "transactionHash": _h(log.get("transactionHash")),
        "transactionIndex": _int(log.get("transactionIndex")),
        "logIndex": _int(log.get("logIndex")),
        "removed": bool(log.get("removed", False)),
    }


def log_key(l: dict) -> tuple:
    return (l["blockHash"], l["transactionHash"], l["logIndex"])


def norm_logs(logs: list) -> list[dict]:
    return sorted((norm_log(l) for l in logs), key=lambda l: (l["blockNumber"], l["logIndex"]))


def compare_logs(answers: dict[str, list]) -> dict:
    """answers: provider -> raw log list (only successful answers).

    Returns per-provider missing / extra / content-mismatch counts against the union.
    A log is 'missing' from a provider if any other provider returned it.
    """
    normed = {p: {log_key(l): l for l in norm_logs(v)} for p, v in answers.items()}
    union = set().union(*[set(d) for d in normed.values()]) if normed else set()
    per = {}
    for p, d in normed.items():
        missing = sorted(union - set(d))
        mism = []
        for k in d:
            others = [o[k] for q, o in normed.items() if q != p and k in o]
            if any(o != d[k] for o in others):
                mism.append(k)
        per[p] = {"count": len(d), "missing": len(missing), "content_mismatch": len(mism),
                  "missing_keys": missing[:20]}
    agree = all(v["missing"] == 0 and v["content_mismatch"] == 0 for v in per.values())
    return {"agree": agree, "union": len(union), "providers": per}


HEADER_SKIP = {"totalDifficulty", "size"}  # optional / provider-computed fields, compared separately


def compare_blocks(answers: dict[str, dict]) -> dict:
    """Compare block headers field by field (transactions compared as hash lists)."""
    norm = {}
    for p, b in answers.items():
        if b is None:
            norm[p] = None
            continue
        d = {k: _h(v) for k, v in b.items() if k not in ("transactions",) and not isinstance(v, (list, dict))}
        txs = b.get("transactions", [])
        d["transactions"] = [_h(t["hash"] if isinstance(t, dict) else t) for t in txs]
        d["withdrawals_n"] = len(b.get("withdrawals", []) or [])
        norm[p] = d
    present = {p: d for p, d in norm.items() if d is not None}
    if len(present) < len(norm):
        return {"agree": False, "null_from": [p for p, d in norm.items() if d is None], "fields": []}
    fields = set().union(*[set(d) for d in present.values()]) - HEADER_SKIP
    diff, presence = [], []
    for f in sorted(fields):
        vals = {p: d.get(f, "<absent>") for p, d in present.items()}
        if len({str(v) for v in vals.values()}) > 1:
            (presence if "<absent>" in vals.values() else diff).append(f)
    return {"agree": not diff, "fields": diff, "presence_only": presence}


def norm_receipt(r: dict) -> dict:
    keep = ("transactionHash", "transactionIndex", "blockHash", "blockNumber", "status",
            "cumulativeGasUsed", "gasUsed", "logsBloom", "contractAddress", "type", "from", "to",
            "effectiveGasPrice")
    out = {k: _h(r.get(k)) for k in keep}
    out["logs"] = norm_logs(r.get("logs", []))
    return out


def compare_receipts(answers: dict[str, dict]) -> dict:
    normed = {p: (norm_receipt(r) if r else None) for p, r in answers.items()}
    vals = list(normed.values())
    if any(v is None for v in vals):
        return {"agree": all(v is None for v in vals), "null_from": [p for p, v in normed.items() if v is None],
                "fields": []}
    fields = sorted({k for v in vals for k in v if len({str(x.get(k)) for x in vals}) > 1})
    return {"agree": not fields, "fields": fields}
