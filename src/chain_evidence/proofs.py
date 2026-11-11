"""Recompute Merkle-Patricia roots and the block hash from provider data.

If receipts reproduce the header's receiptsRoot, and the header reproduces the
block hash, the receipt set (and every log in it) is complete and unaltered -
no provider has to be trusted for that, only the block hash.
"""
import rlp
from eth_hash.auto import keccak
from trie import HexaryTrie

# OP-stack deposit transactions (Base etc.), see OP specs "deposits".
DEPOSIT_TX_TYPE = 0x7E


def _b(x) -> bytes:
    """hex string -> bytes; quantities are minimal big-endian (RLP integer encoding)."""
    if x is None:
        return b""
    s = x[2:] if x.startswith("0x") else x
    if len(s) % 2:
        s = "0" + s
    return bytes.fromhex(s)


def _q(x) -> int:
    return int(x, 16) if x not in (None, "0x", "") else 0


def encode_receipt(r: dict) -> bytes:
    logs = [[_b(l["address"]), [_b(t) for t in l["topics"]], _b(l["data"])] for l in r["logs"]]
    first = _b(r["root"]) if r.get("root") and not r.get("status") else _q(r.get("status"))
    fields = [first, _q(r["cumulativeGasUsed"]), _b(r["logsBloom"]), logs]
    t = _q(r.get("type", "0x0"))
    if t == DEPOSIT_TX_TYPE:
        # Regolith adds depositNonce, Canyon adds depositReceiptVersion (OP specs).
        if r.get("depositNonce") is not None:
            fields.append(_q(r["depositNonce"]))
        if r.get("depositReceiptVersion") is not None:
            fields.append(_q(r["depositReceiptVersion"]))
    enc = rlp.encode(fields)
    return enc if t == 0 else bytes([t]) + enc


def _access_list(al):
    return [[_b(e["address"]), [_b(k) for k in e["storageKeys"]]] for e in (al or [])]


def _sig(tx):
    y = tx.get("yParity", tx.get("v"))
    return [_q(y), _q(tx["r"]), _q(tx["s"])]


def encode_tx(tx: dict) -> bytes:
    t = _q(tx.get("type", "0x0"))
    to = _b(tx.get("to")) if tx.get("to") else b""
    common_tail = [_q(tx["gas"]), to, _q(tx["value"]), _b(tx["input"])]
    if t == 0:
        return rlp.encode([_q(tx["nonce"]), _q(tx["gasPrice"]), *common_tail,
                           _q(tx["v"]), _q(tx["r"]), _q(tx["s"])])
    if t == 1:
        body = [_q(tx["chainId"]), _q(tx["nonce"]), _q(tx["gasPrice"]), *common_tail,
                _access_list(tx.get("accessList")), *_sig(tx)]
    elif t in (2, 3, 4):
        body = [_q(tx["chainId"]), _q(tx["nonce"]), _q(tx["maxPriorityFeePerGas"]),
                _q(tx["maxFeePerGas"]), *common_tail, _access_list(tx.get("accessList"))]
        if t == 3:
            body += [_q(tx["maxFeePerBlobGas"]), [_b(h) for h in tx["blobVersionedHashes"]]]
        if t == 4:
            body.append([[_q(a["chainId"]), _b(a["address"]), _q(a["nonce"]), _q(a["yParity"]),
                          _q(a["r"]), _q(a["s"])] for a in tx["authorizationList"]])
        body += _sig(tx)
    elif t == DEPOSIT_TX_TYPE:
        body = [_b(tx["sourceHash"]), _b(tx["from"]), to, _q(tx.get("mint", "0x0")), _q(tx["value"]),
                _q(tx["gas"]), 1 if tx.get("isSystemTx") else 0, _b(tx["input"])]
    else:
        raise ValueError(f"unsupported tx type {t:#x}")
    return bytes([t]) + rlp.encode(body)


def trie_root(items: list[bytes]) -> str:
    t = HexaryTrie({})
    for i, v in enumerate(items):
        t[rlp.encode(i)] = v
    return "0x" + t.root_hash.hex()


def receipts_root(receipts: list[dict]) -> str:
    receipts = sorted(receipts, key=lambda r: _q(r["transactionIndex"]))
    return trie_root([encode_receipt(r) for r in receipts])


def transactions_root(txs: list[dict]) -> str:
    txs = sorted(txs, key=lambda t: _q(t["transactionIndex"]))
    return trie_root([encode_tx(t) for t in txs])


# Header fields in consensus order; trailing fields are present only after their fork.
HEADER_ORDER = [
    ("parentHash", "b"), ("sha3Uncles", "b"), ("miner", "b"), ("stateRoot", "b"),
    ("transactionsRoot", "b"), ("receiptsRoot", "b"), ("logsBloom", "b"), ("difficulty", "q"),
    ("number", "q"), ("gasLimit", "q"), ("gasUsed", "q"), ("timestamp", "q"), ("extraData", "b"),
    ("mixHash", "b"), ("nonce", "b"), ("baseFeePerGas", "q"), ("withdrawalsRoot", "b"),
    ("blobGasUsed", "q"), ("excessBlobGas", "q"), ("parentBeaconBlockRoot", "b"), ("requestsHash", "b"),
    ("blockAccessListHash", "b"),
]


def header_hash(block: dict) -> str:
    fields = []
    for name, kind in HEADER_ORDER:
        if name not in block or block[name] is None:
            if name in ("parentHash", "number"):
                raise ValueError(f"header missing {name}")
            break  # first absent optional field ends the list
        fields.append(_b(block[name]) if kind == "b" else _q(block[name]))
    return "0x" + keccak(rlp.encode(fields)).hex()


def verify_block(block: dict, receipts: list[dict] | None) -> dict:
    """block must include full transaction objects."""
    out = {"number": _q(block["number"]), "hash": block["hash"].lower()}
    out["header_hash_ok"] = header_hash(block) == block["hash"].lower()
    txs = block.get("transactions", [])
    if txs and isinstance(txs[0], dict):
        out["transactions_root_ok"] = transactions_root(txs) == block["transactionsRoot"].lower()
    if receipts is not None:
        out["receipts_n"] = len(receipts)
        out["receipts_root_ok"] = receipts_root(receipts) == block["receiptsRoot"].lower()
        out["receipts_block_hash_ok"] = all(r["blockHash"].lower() == out["hash"] for r in receipts)
    return out
