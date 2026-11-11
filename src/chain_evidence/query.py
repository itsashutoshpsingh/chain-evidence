"""Send the same JSON-RPC request to every provider, with polite pacing and retries.

Transport failures, rate limits and provider policy refusals are *errors*, never
recorded as data. Only a successful `result` is ever compared.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import requests

from .providers import Provider

# Messages that mean "try again later", not "this is the answer".
TRANSIENT = ("rate limit", "too many", "capacity", "timeout", "timed out", "temporarily",
             "try again", "busy", "overloaded", "method not available", "upstream",
             "internal error", "bad gateway", "unavailable")
_locks: dict[str, threading.Lock] = {}
_last: dict[str, float] = {}
_session = requests.Session()


@dataclass
class Answer:
    provider: str
    method: str
    params: list
    ok: bool
    result: object = None
    error: str | None = None
    attempts: int = 0
    sent_at: str = ""
    received_at: str = ""
    latency_ms: float = 0.0

    def to_dict(self):
        return asdict(self)


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _pace(p: Provider):
    lock = _locks.setdefault(p.name + p.chain, threading.Lock())
    with lock:
        wait = _last.get(p.name + p.chain, 0) + p.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[p.name + p.chain] = time.monotonic()


def is_transient(msg: str) -> bool:
    m = msg.lower()
    return any(t in m for t in TRANSIENT)


def call(p: Provider, method: str, params: list, retries: int = 5, timeout: float = 60) -> Answer:
    ans = Answer(p.name, method, params, ok=False)
    for attempt in range(1, retries + 1):
        _pace(p)
        ans.attempts = attempt
        ans.sent_at = _utc()
        t0 = time.monotonic()
        try:
            r = _session.post(p.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                              headers={"content-type": "application/json", **p.headers}, timeout=timeout)
            ans.latency_ms = round((time.monotonic() - t0) * 1000, 1)
            ans.received_at = _utc()
            if r.status_code == 429 or r.status_code >= 500:
                ans.error = f"HTTP {r.status_code}"
            else:
                body = r.json()
                if "error" in body and body["error"]:
                    e = body["error"]
                    ans.error = f"{e.get('code')}: {e.get('message')}" if isinstance(e, dict) else str(e)
                    if not is_transient(ans.error):
                        return ans  # policy refusal (range too large etc.): final, but still an error
                elif "result" in body:
                    ans.ok, ans.result, ans.error = True, body["result"], None
                    return ans
                else:
                    ans.error = "malformed response"
        except (requests.RequestException, ValueError) as ex:
            ans.received_at = _utc()
            ans.error = f"{type(ex).__name__}: {ex}"[:300]
        time.sleep(min(2 ** attempt, 30))
    return ans


def call_all(providers: list[Provider], method: str, params: list, **kw) -> dict[str, Answer]:
    with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
        futs = {p.name: ex.submit(call, p, method, params, **kw) for p in providers}
        return {name: f.result() for name, f in futs.items()}
