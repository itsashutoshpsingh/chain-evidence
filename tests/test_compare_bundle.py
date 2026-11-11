import copy

from chain_evidence import bundle, compare, finality
from chain_evidence.providers import Provider
from chain_evidence.query import Answer, is_transient


def _logs(fx):
    return [l for r in fx["receipts"] for l in r["logs"]]


def test_identical_answers_agree(block_fixture):
    logs = _logs(block_fixture)
    res = compare.compare_logs({"a": logs, "b": list(reversed(logs))})
    assert res["agree"] and res["union"] == len(logs)


def test_missing_log_attributed_to_right_provider(block_fixture):
    logs = _logs(block_fixture)
    if not logs:
        return
    res = compare.compare_logs({"a": logs, "b": logs[1:]})
    assert not res["agree"]
    assert res["providers"]["b"]["missing"] == 1 and res["providers"]["a"]["missing"] == 0


def test_content_mismatch(block_fixture):
    logs = _logs(block_fixture)
    if not logs:
        return
    bad = copy.deepcopy(logs)
    bad[0]["data"] = "0xdead"
    res = compare.compare_logs({"a": logs, "b": bad})
    assert res["providers"]["b"]["content_mismatch"] == 1


def test_header_diff(block_fixture):
    b = block_fixture["block"]
    other = copy.deepcopy(b)
    other["stateRoot"] = "0x" + "11" * 32
    assert compare.compare_blocks({"a": b, "b": other})["fields"] == ["stateRoot"]
    assert compare.compare_blocks({"a": b, "b": copy.deepcopy(b)})["agree"]


def test_bundle_detects_tampering():
    p = [Provider("x", "ethereum", "https://example.invalid/abcdefghijklmnopqrstuvwxyz123456")]
    a = {"x": Answer("x", "eth_blockNumber", [], ok=True, result="0x10")}
    b = bundle.make("ethereum", {"method": "eth_blockNumber"}, a, p, {"agree": True})
    assert bundle.verify(b) == []
    assert "<redacted>" in b["responses"][0]["endpoint"]
    b["responses"][0]["result"] = "0x11"
    assert len(bundle.verify(b)) == 2


def test_finality_floor_is_conservative():
    h = {"a": {"finalized": 100}, "b": {"finalized": 90}, "c": {"finalized": None}}
    assert finality.finalized_floor(h) == 90
    assert finality.is_final(90, h) and not finality.is_final(91, h)


def test_transient_classification():
    assert is_transient("-32005: Rate limit exceeded on Nodies public endpoints")
    assert is_transient("-32000: method not available")
    assert not is_transient("-32602: eth_getLogs is limited to 0 - 50 blocks range")
