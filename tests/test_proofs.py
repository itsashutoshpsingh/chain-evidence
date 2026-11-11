import copy

from chain_evidence import proofs


def test_real_blocks_verify(block_fixture):
    v = proofs.verify_block(block_fixture["block"], block_fixture["receipts"])
    assert v["header_hash_ok"] and v["transactions_root_ok"] and v["receipts_root_ok"]


def test_dropped_log_is_detected(block_fixture):
    r = copy.deepcopy(block_fixture["receipts"])
    victim = next(x for x in r if x["logs"])
    victim["logs"].pop()
    assert not proofs.verify_block(block_fixture["block"], r)["receipts_root_ok"]


def test_dropped_receipt_is_detected(block_fixture):
    r = copy.deepcopy(block_fixture["receipts"])[:-1]
    assert not proofs.verify_block(block_fixture["block"], r)["receipts_root_ok"]


def test_edited_header_breaks_hash(block_fixture):
    b = copy.deepcopy(block_fixture["block"])
    b["receiptsRoot"] = "0x" + "00" * 32
    assert not proofs.verify_block(b, None)["header_hash_ok"]


def test_empty_trie_root():
    # keccak(rlp(b"")) - the well-known empty trie root
    assert proofs.trie_root([]) == "0x56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421"
