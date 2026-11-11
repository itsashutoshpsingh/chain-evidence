"""Adjudication end to end, against a fake provider that serves a recorded block."""
from chain_evidence import checks, query
from chain_evidence.providers import Provider


def _fake(fx):
    blk, rec = fx["block"], fx["receipts"]
    n = blk["number"]

    def call(p, method, params, **kw):
        if method == "eth_getBlockByNumber" and params[0] == n:
            res = blk if params[1] else {**blk, "transactions": [t["hash"] for t in blk["transactions"]]}
        elif method == "eth_getBlockReceipts" and params[0] == n:
            res = rec
        else:
            return query.Answer(p.name, method, params, ok=False, error="not in fixture")
        return query.Answer(p.name, method, params, ok=True, result=res)
    return call


def test_adjudication_names_the_provider_that_dropped_a_log(block_fixture, monkeypatch):
    fake = _fake(block_fixture)
    monkeypatch.setattr(checks, "call", fake)
    monkeypatch.setattr(checks, "call_all", lambda ps, m, prm, **kw: {p.name: fake(p, m, prm) for p in ps})
    ps = [Provider("a", "x", "u"), Provider("b", "x", "u")]
    logs = [l for r in block_fixture["receipts"] for l in r["logs"]]
    if not logs:
        return
    n = int(block_fixture["block"]["number"], 16)
    out = checks.adjudicate_logs(ps, n, n, answers={"a": logs, "b": logs[:-1]})
    assert out["proven"] and out["true_count"] == len(logs)
    assert out["providers"]["a"] == {"missing": 0, "content_mismatch": 0, "extra": 0}
    assert out["providers"]["b"]["missing"] == 1


def test_tampered_receipts_are_not_accepted_as_proof(block_fixture, monkeypatch):
    fx = {"block": block_fixture["block"], "receipts": block_fixture["receipts"][:-1]}
    fake = _fake(fx)
    monkeypatch.setattr(checks, "call", fake)
    monkeypatch.setattr(checks, "call_all", lambda ps, m, prm, **kw: {p.name: fake(p, m, prm) for p in ps})
    n = int(fx["block"]["number"], 16)
    assert not checks.adjudicate_logs([Provider("a", "x", "u")], n, n, answers={})["proven"]
