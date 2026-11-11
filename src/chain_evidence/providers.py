"""Load RPC provider definitions from providers.toml (falls back to the example)."""
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Provider:
    name: str
    chain: str
    url: str
    min_interval: float = 1.0
    headers: dict = field(default_factory=dict)

    @property
    def redacted_url(self) -> str:
        """URL safe to store in an evidence bundle (path segments that look like keys removed)."""
        return re.sub(r"/[A-Za-z0-9_\-]{20,}", "/<redacted>", self.url)


def _expand(value: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def load(chain: str | None = None, path: str | os.PathLike | None = None) -> list[Provider]:
    if path is None:
        path = ROOT / "providers.toml"
        if not path.exists():
            path = ROOT / "providers.example.toml"
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    out = []
    for p in cfg.get("provider", []):
        needed = re.findall(r"\$\{(\w+)\}", p["url"] + "".join(p.get("headers", {}).values()))
        if any(not os.environ.get(v) for v in needed):
            continue  # key variable unset: skip rather than send an unauthenticated request
        url = _expand(p["url"])
        prov = Provider(p["name"], p["chain"], url, float(p.get("min_interval", 1.0)),
                        {k: _expand(v) for k, v in p.get("headers", {}).items()})
        if chain is None or prov.chain == chain:
            out.append(prov)
    return out
