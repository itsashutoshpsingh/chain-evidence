"""Is a block finalised? Ask every provider for its `finalized` head; trust the lowest."""
from .query import call_all


def heads(providers) -> dict:
    """provider -> {"finalized": n, "latest": n}; None where the provider failed."""
    out = {p.name: {} for p in providers}
    for tag in ("finalized", "latest"):
        for name, a in call_all(providers, "eth_getBlockByNumber", [tag, False]).items():
            out[name][tag] = int(a.result["number"], 16) if a.ok and a.result else None
    return out


def finalized_floor(h: dict) -> int | None:
    """Conservative: a block is final only if *every* responding provider says so."""
    vals = [v["finalized"] for v in h.values() if v.get("finalized") is not None]
    return min(vals) if vals else None


def is_final(block: int, h: dict) -> bool:
    floor = finalized_floor(h)
    return floor is not None and block <= floor
