"""Sample every provider's latest/finalized head at a fixed interval (appends to results/heads_<chain>.csv)."""
import sys
import time
from datetime import datetime, timezone

from chain_evidence import finality, providers, survey

chain, n, every = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
ps = providers.load(chain)
for i in range(n):
    run_id = "heads-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    h = finality.heads(ps)
    survey._append(f"heads_{chain}.csv", [{"run_id": run_id, "provider": p, **v} for p, v in h.items()])
    print(run_id, h, flush=True)
    time.sleep(every)
