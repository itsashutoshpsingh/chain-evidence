"""Evidence bundles: what was asked, what every provider answered, when, and hashes.

The bundle hash covers every other field, so any later edit is detectable.
"""
import hashlib
import json
from datetime import datetime, timezone

from . import __version__

SCHEMA = "chain-evidence/bundle/v1"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def make(chain: str, request: dict, answers: dict, providers: list, comparison: dict,
         finality: dict | None = None, proofs: dict | None = None) -> dict:
    urls = {p.name: p.redacted_url for p in providers}
    responses = []
    for name, a in answers.items():
        d = a.to_dict()
        d["endpoint"] = urls.get(name)
        d["result_sha256"] = sha256(a.result) if a.ok else None
        responses.append(d)
    b = {
        "schema": SCHEMA,
        "tool": f"chain-evidence {__version__}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chain": chain,
        "request": request,
        "responses": responses,
        "comparison": comparison,
        "finality": finality,
        "proofs": proofs,
    }
    b["bundle_sha256"] = sha256(b)
    return b


def verify(b: dict) -> list[str]:
    """Return a list of problems; empty means the bundle is intact."""
    problems = []
    body = {k: v for k, v in b.items() if k != "bundle_sha256"}
    if sha256(body) != b.get("bundle_sha256"):
        problems.append("bundle_sha256 does not match contents")
    for r in b.get("responses", []):
        if r.get("ok") and sha256(r.get("result")) != r.get("result_sha256"):
            problems.append(f"result_sha256 mismatch for provider {r.get('provider')}")
    return problems
