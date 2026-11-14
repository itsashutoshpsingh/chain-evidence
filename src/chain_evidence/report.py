"""Turn results/*.csv into the README tables, docs/img charts and results/summary.json."""
import csv
import json
import math
from collections import Counter, defaultdict

from .providers import ROOT

RES, IMG = ROOT / "results", ROOT / "docs" / "img"
# Portfolio chart style (BUILD_RULES.md, "Charts"): solid colours, Carlito, capitalised labels.
BG, FG, FG2, GRID = "#0C1421", "#FFFFFF", "#C9D4E2", "#1F2E45"
BLUE, GREEN, RED, YELLOW, WHITE = "#3B82F6", "#22C55E", "#EF4444", "#FACC15", "#FFFFFF"
CHAIN = {"ethereum": "Ethereum", "base": "Base"}
POLICY = ("usage limit", "archive", "limited to", "must not exceed", "specify an address", "not supported on free",
          "discontinued", "not allowed", "personal token", "pruned")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def rows(name):
    p = RES / name
    return list(csv.DictReader(open(p))) if p.exists() else []


def classify(err: str) -> str:
    e = err.lower()
    return "refused (policy)" if any(k in e for k in POLICY) else "failed (after retries)"


def logs_stats(data, chain):
    out = {"chain": chain}
    d = [r for r in data if r["chain"] == chain]
    final = [r for r in d if r["kind"] in ("final", "final_deep")]
    comp = [r for r in final if len(json.loads(r["per_provider"])) >= 2]
    dis = [r for r in comp if r["agree"] == "False"]
    head = [r for r in d if r["kind"] == "near_head"]
    head_comp = [r for r in head if len(json.loads(r["per_provider"])) >= 2]
    head_dis = [r for r in head_comp if r["agree"] == "False"]
    missing = sum(sum(v[1] for v in json.loads(r["per_provider"]).values()) for r in dis)
    p, lo, hi = wilson(len(dis), len(comp))
    adj = [json.loads(r["adjudication"]) for r in dis if r["adjudication"]]
    wrong = Counter()
    for a in adj:
        for prov, v in a.get("providers", {}).items():
            if v["missing"] or v["content_mismatch"] or v["extra"]:
                wrong[prov] += 1
    out.update(
        runs=sorted({r["run_id"] for r in d}), ranges=len(final), comparable=len(comp), disagreements=len(dis),
        rate=p, ci=[lo, hi], missing_logs=missing, empty_success=sum(1 for r in final if r["empty_success"]),
        header_checked=sum(1 for r in final if r["header_agree"] in ("True", "False")),
        header_disagree=sum(1 for r in final if r["header_agree"] == "False"),
        near_head=len(head), near_head_comparable=len(head_comp), near_head_disagree=len(head_dis),
        adjudicated=len(adj), proven=sum(1 for a in adj if a.get("proven")), wrong_by_provider=dict(wrong),
        deep_ranges=sum(1 for r in final if r["kind"] == "final_deep"),
        deep_comparable=sum(1 for r in comp if r["kind"] == "final_deep"),
    )
    # provider outcomes over every request (final + near head)
    outcome = defaultdict(Counter)
    provs = {r["provider"] for r in rows(f"heads_{chain}.csv")}
    for r in d:
        per, errs = json.loads(r["per_provider"]), json.loads(r["errors"])
        for prov in provs - set(per) - set(errs):
            outcome[prov]["answered, no second answer to compare"] += 1
        for prov, e in errs.items():
            outcome[prov][classify(e)] += 1
        for prov, (cnt, miss, mism) in per.items():
            outcome[prov]["answered, differs" if (miss or mism) else "answered, matches"] += 1
    out["outcomes"] = {k: dict(v) for k, v in outcome.items()}
    err_text = defaultdict(Counter)
    for r in d:
        for prov, e in json.loads(r["errors"]).items():
            err_text[prov][e[:90]] += 1
    out["error_messages"] = {k: v.most_common(6) for k, v in err_text.items()}
    for kind in ("final", "final_deep"):
        c = [r for r in comp if r["kind"] == kind]
        k = [r for r in c if r["agree"] == "False"]
        p_, lo_, hi_ = wilson(len(k), len(c))
        out[kind] = {"ranges": sum(1 for r in final if r["kind"] == kind), "comparable": len(c),
                     "disagreements": len(k), "rate": p_, "ci": [lo_, hi_],
                     "missing_logs": sum(sum(v[1] for v in json.loads(r["per_provider"]).values()) for r in k),
                     "empty_success": sum(1 for r in k if r["empty_success"])}
    per_run = []
    for run in out["runs"]:
        c = [r for r in comp if r["run_id"] == run]
        if len(c) < 20:
            continue  # interrupted runs: their rows count in totals, but a per-run rate would be noise
        k = sum(1 for r in c if r["agree"] == "False")
        per_run.append({"run_id": run, "n": len(c), "k": k, **dict(zip(("rate", "lo", "hi"), wilson(k, len(c))))})
    out["per_run"] = per_run
    return out


def _style(plt):
    plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
                         "text.color": FG, "axes.labelcolor": FG, "xtick.color": FG2, "ytick.color": FG2,
                         "axes.edgecolor": GRID, "grid.color": GRID, "font.family": "Carlito",
                         "font.size": 11, "axes.titleweight": "bold", "axes.titlesize": 15, "axes.labelsize": 12,
                         "xtick.labelsize": 11, "ytick.labelsize": 11, "legend.fontsize": 11, "legend.labelcolor": FG,
                         "axes.axisbelow": True})


def charts(stats, roots):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    IMG.mkdir(parents=True, exist_ok=True)
    made = []
    # 1. hero: what each provider did with every request
    cats = [("answered, matches", GREEN), ("answered, differs", RED),
            ("answered, no second answer to compare", BLUE), ("refused (policy)", YELLOW),
            ("failed (after retries)", WHITE)]
    labels, data = [], []
    for s in stats:
        for prov, o in sorted(s["outcomes"].items()):
            labels.append(f"{CHAIN[s['chain']]}/{prov}")
            data.append(o)
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(labels) + 1.6))
    left = [0] * len(labels)
    for cat, col in cats:
        vals = [d.get(cat, 0) / max(1, sum(d.values())) * 100 for d in data]
        ax.barh(labels, vals, left=left, color=col, label=cat[0].upper() + cat[1:], height=0.6)
        for i, v in enumerate(vals):
            if v >= 7:
                ax.text(left[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", color=BG, fontsize=11,
                        fontweight="bold")
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Requests (%)")
    ax.set_title("Providers rarely disagreed; most failures were refusals, not wrong answers", loc="left")
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.2), frameon=False)
    ax.grid(axis="x")
    fig.tight_layout()
    fig.savefig(IMG / "provider_outcomes.png", dpi=200)
    plt.close(fig)
    made.append("docs/img/provider_outcomes.png")
    # 2. disagreement rate per run with Wilson CI
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = 0
    ticks, names = [], []
    for s, col in zip(stats, (GREEN, BLUE)):
        for pr in s["per_run"]:
            ax.errorbar([x], [pr["rate"] * 100], yerr=[[100 * (pr["rate"] - pr["lo"])], [100 * (pr["hi"] - pr["rate"])]],
                        fmt="o", color=col, ecolor=col, capsize=5, ms=7)
            ax.text(x + 0.08, pr["rate"] * 100, f" {pr['k']}/{pr['n']}", va="center", fontsize=11)
            ticks.append(x)
            names.append(f"{CHAIN[s['chain']]}\n{pr['run_id'][9:13]}Z")
            x += 1
        x += 0.6
    ax.set_xticks(ticks, names, fontsize=11)
    ax.set_ylabel("Finalised ranges that disagree (%)")
    worst = max((pr for s in stats for pr in s["per_run"]), key=lambda pr: pr["rate"], default=None)
    ax.set_title(f"The worst run had {worst['k']} of {worst['n']} finalised ranges disagree (95% Wilson interval)"
                 if worst else "Disagreement rate per run (95% Wilson interval)", loc="left")
    ax.grid(axis="y")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(IMG / "disagreement_rate.png", dpi=200)
    plt.close(fig)
    made.append("docs/img/disagreement_rate.png")
    # 3. finalised-head lag per provider
    lag_rows = []
    for chain in ("ethereum", "base"):
        h = rows(f"heads_{chain}.csv")
        by = defaultdict(dict)
        for r in h:
            if r["finalized"]:
                by[r["run_id"]][r["provider"]] = int(r["finalized"])
        for run, d in by.items():
            top = max(d.values())
            for prov, v in d.items():
                lag_rows.append((chain, prov, top - v))
    if lag_rows:
        agg = defaultdict(list)
        for chain, prov, lag in lag_rows:
            agg[f"{chain}/{prov}"].append(lag)
        fig, ax = plt.subplots(figsize=(9, 0.5 * len(agg) + 1.4))
        ks = sorted(agg)
        mx = [max(agg[k]) for k in ks]
        ax.barh([CHAIN[k.split("/")[0]] + k[k.index("/"):] for k in ks], mx, color=[RED if m > 64 else GREEN for m in mx],
                height=0.55)
        for i, k in enumerate(ks):
            ax.text(mx[i], i, f"  Max {mx[i]} blocks behind (n={len(agg[k])} runs)", va="center", fontsize=11)
        ax.invert_yaxis()
        ax.set_xlabel("Blocks behind the most advanced provider's `finalized` head")
        ax.set_title(f"A provider's `finalized` head can lag up to {max(mx):,} blocks behind the others", loc="left")
        ax.grid(axis="x")
        ax.set_xlim(0, max(mx) * 1.6 + 5)
        fig.tight_layout()
        fig.savefig(IMG / "finalized_lag.png", dpi=200)
        plt.close(fig)
        made.append("docs/img/finalized_lag.png")
    # 4. receipts-root proofs per provider
    if roots:
        agg = defaultdict(Counter)
        for r in roots:
            k = f"{r['chain']}/{r['provider']}"
            if r.get("receipts_null") == "True":
                agg[k]["null receipts (success, no data)"] += 1
            elif r["error"]:
                agg[k]["not checked"] += 1
            elif r["receipts_root_ok"] == "True" and r["header_hash_ok"] == "True" and r["transactions_root_ok"] == "True":
                agg[k]["all roots reproduce"] += 1
            else:
                agg[k]["root mismatch"] += 1
        ks = sorted(agg)
        fig, ax = plt.subplots(figsize=(10, 0.5 * len(ks) + 1.6))
        left = [0] * len(ks)
        for cat, col in (("all roots reproduce", GREEN), ("root mismatch", RED),
                         ("null receipts (success, no data)", YELLOW), ("not checked", WHITE)):
            vals = [agg[k].get(cat, 0) for k in ks]
            ax.barh([CHAIN[k.split("/")[0]] + k[k.index("/"):] for k in ks], vals, left=left, color=col,
                    label=cat[0].upper() + cat[1:], height=0.55)
            left = [a + b for a, b in zip(left, vals)]
        ax.invert_yaxis()
        ax.set_xlabel("Blocks")
        ax.set_title("No checked block failed to reproduce its header hash, transactionsRoot and receiptsRoot"
                     if not any(a.get("root mismatch") for a in agg.values())
                     else "Header hash, transactionsRoot and receiptsRoot recomputed locally", loc="left")
        ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False)
        fig.tight_layout()
        fig.savefig(IMG / "receipts_root_proofs.png", dpi=200)
        plt.close(fig)
        made.append("docs/img/receipts_root_proofs.png")
    # 5. how deep does publicnode keep receipts? (sampled Ethereum transactions)
    tx = [r for r in rows("tx_survey.csv") if r["chain"] == "ethereum" and r.get("block") and r.get("finalized_floor")]
    if tx:
        fig, ax = plt.subplots(figsize=(10, 3))
        for null, col, lab in ((False, GREEN, "Receipt returned"), (True, RED, "`null` receipt (success, no data)")):
            xs = [(int(r["finalized_floor"]) - int(r["block"])) / 7200 for r in tx
                  if ("publicnode" in r.get("null_receipt_from", "")) == null]
            ax.scatter(xs, [0.5 + (0.12 if null else -0.12)] * len(xs), s=46, color=col,
                       label=f"{lab} (n={len(xs)})", edgecolors=BG)
        ax.set_yticks([])
        ax.set_ylim(0, 1)
        ax.set_xlabel("Age of the transaction's block (days behind the finalised head, 7,200 blocks/day)")
        ax.set_title("publicnode silently returns `null` receipts for blocks older than about 6 days", loc="left")
        ax.legend(loc="upper left", frameon=False)
        ax.grid(axis="x")
        fig.tight_layout()
        fig.savefig(IMG / "receipt_depth.png", dpi=200)
        plt.close(fig)
        made.append("docs/img/receipt_depth.png")
    return made


def root_stats(roots):
    out = defaultdict(Counter)
    for r in roots:
        k = (r["chain"], r["provider"])
        if r.get("receipts_null") == "True":
            out[k]["null_receipts"] += 1
            continue
        if r["error"]:
            out[k]["not_checked"] += 1
            continue
        out[k]["checked"] += 1
        out[k]["header_ok"] += r["header_hash_ok"] == "True"
        out[k]["txroot_ok"] += r["transactions_root_ok"] == "True"
        out[k]["rroot_ok"] += r["receipts_root_ok"] == "True"
        if r["getlogs_missing"] not in ("", None):
            out[k]["getlogs_checked"] += 1
            out[k]["getlogs_bad"] += (r["getlogs_missing"] != "0" or r["getlogs_mismatch"] != "0"
                                      or r["getlogs_extra"] != "0")
    return {f"{c}/{p}": dict(v) for (c, p), v in out.items()}


def finality_lag(chain, block_seconds):
    """latest - finalized per sample (max over providers' latest, per provider's finalized)."""
    by = defaultdict(dict)
    for r in rows(f"heads_{chain}.csv"):
        if r["finalized"] and r["latest"]:
            by[r["run_id"]][r["provider"]] = (int(r["finalized"]), int(r["latest"]))
    lags, spread = [], []
    for run, d in by.items():
        top = max(l for _, l in d.values())
        fins = [f for f, _ in d.values()]
        lags.append(top - max(fins))
        spread.append(max(fins) - min(fins))
    if not lags:
        return None
    lags.sort()
    return {"samples": len(lags), "median_blocks": lags[len(lags) // 2], "min_blocks": lags[0], "max_blocks": lags[-1],
            "median_minutes": round(lags[len(lags) // 2] * block_seconds / 60, 1),
            "max_provider_finalized_spread_blocks": max(spread),
            "samples_with_spread": sum(1 for x in spread if x)}


def main():
    data = rows("logs_survey.csv")
    roots = rows("root_survey.csv")
    txs = rows("tx_survey.csv")
    stats = [logs_stats(data, c) for c in ("ethereum", "base") if any(r["chain"] == c for r in data)]
    rs = root_stats(roots)
    tx = {c: {"checked": sum(1 for r in txs if r["chain"] == c),
              "disagree": sum(1 for r in txs if r["chain"] == c and r["agree"] == "False"),
              "proved": sum(1 for r in txs if r["chain"] == c and r["proof"] and '"receipts_root_ok": true' in r["proof"])}
          for c in ("ethereum", "base")}
    made = charts(stats, roots)
    table = ["| Chain | Ranges checked | Comparable (≥2 answers) | Disagreements | Missing logs | Not finalised (checked separately) |",
             "|---|---|---|---|---|---|"]
    for s in stats:
        for kind, label in (("final", "recent"), ("final_deep", "deep history")):
            k = s[kind]
            table.append(f"| {s['chain']} ({label}) | {k['ranges']} | {k['comparable']} | {k['disagreements']} "
                         f"({100 * k['rate']:.1f}%, 95% CI {100 * k['ci'][0]:.1f}–{100 * k['ci'][1]:.1f}%) | "
                         f"{k['missing_logs']} | {s['near_head'] if kind == 'final' else '—'}"
                         f"{' (' + str(s['near_head_disagree']) + ' disagreed)' if kind == 'final' else ''} |")
    rt = ["| Provider | Blocks checked | Header hash | transactionsRoot | receiptsRoot | eth_getLogs vs proven receipts | `null` receipts (success, no data) | Not checked (refused / quota) |",
          "|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(rs.items()):
        n = v.get("checked", 0)
        gl = f"{v.get('getlogs_checked', 0) - v.get('getlogs_bad', 0)}/{v.get('getlogs_checked', 0)} match" \
            if v.get("getlogs_checked") else "n/a"
        rt.append(f"| {k} | {n} | {v.get('header_ok', 0)}/{n} | {v.get('txroot_ok', 0)}/{n} | "
                  f"{v.get('rroot_ok', 0)}/{n} | {gl} | {v.get('null_receipts', 0)} | {v.get('not_checked', 0)} |")
    (RES / "summary.md").write_text("\n".join(table) + "\n\n" + "\n".join(rt) + "\n")
    eth = next((s for s in stats if s["chain"] == "ethereum"), None)
    summary = {
        "project": "chain-evidence",
        "headline": (f"Asked {len(eth['outcomes']) if eth else 0} Ethereum providers the same eth_getLogs question "
                     f"across {eth['ranges'] if eth else 0} finalised block ranges; "
                     f"{eth['disagreements'] if eth else 0} of {eth['comparable'] if eth else 0} comparable ranges disagreed.")
        if eth else "",
        "metrics": [],
        "stats": stats, "roots": rs, "tx": tx, "charts": made,
        "finality_lag": {"ethereum": finality_lag("ethereum", 12), "base": finality_lag("base", 2)},
    }
    for s in stats:
        summary["metrics"] += [
            {"label": f"{CHAIN[s['chain']]} finalised ranges compared", "value": s["comparable"]},
            {"label": f"{CHAIN[s['chain']]} disagreement rate", "value": f"{100 * s['rate']:.1f}% (95% CI {100 * s['ci'][0]:.1f}–{100 * s['ci'][1]:.1f}%)"},
            {"label": f"{CHAIN[s['chain']]} empty successes (0 logs where logs exist)", "value": s["empty_success"]},
        ]
    for k, v in sorted(rs.items()):
        chain, prov = k.split("/", 1)
        summary["metrics"].append({"label": f"{CHAIN[chain]} blocks from {prov} whose receipts reproduce receiptsRoot",
                                   "value": f"{v.get('rroot_ok', 0)}/{v.get('checked', 0)}"})
    (RES / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print((RES / "summary.md").read_text())
    print(json.dumps(summary["finality_lag"]))
    print(json.dumps({s["chain"]: {k: s[k] for k in ("ranges", "comparable", "disagreements", "rate", "ci",
                                                       "empty_success", "near_head", "near_head_disagree",
                                                       "deep_ranges", "deep_comparable", "wrong_by_provider")}
                      for s in stats}, indent=1, default=str))


if __name__ == "__main__":
    main()
