"""Render an engine report as a Markdown incident record (what happened, evidence, impact, next steps)."""
from __future__ import annotations

def _ms(x: float) -> str: return f"{x/1000:.2f}s" if x >= 1000 else f"{x:.0f}ms"

def _next_steps(e: dict, target: str) -> list[str]:
    steps = []
    if e["p99_lift"] >= 3: steps.append(f"Latency on calls into `{target}` is {1+e['p99_lift']:.1f}x its baseline: check `{target}` for resource saturation, slow dependencies and recent changes.")
    if e["error_rate"] >= .05: steps.append(f"`{target}` fails {e['error_rate']*100:.1f}% of calls: inspect its error logs and any deployment or configuration change near the onset.")
    if e["retry_mean"] >= .2: steps.append(f"Callers retry {e['retry_mean']:.2f} times per call on average: review retry/backoff policy to avoid amplifying the load.")
    return steps or ["Evidence is weak; widen the observation window and re-run before escalating."]

def incident_markdown(data: dict, threshold: float = 15.0, window_s: float | None = None, injected: dict | None = None,
                      detected_at_s: float | None = None) -> str:
    rank = data.get("ranking", []); top = rank[0] if rank else None
    out = ["# Incident report", ""]
    if not top or top["score"] < threshold:
        out += ["**Status:** no incident detected.", "",
                f"No edge crossed the detection threshold ({top['score']:.1f} of {threshold:g})." if top else "No degraded edge was found in the supplied spans."]
        return "\n".join(out) + "\n"
    e, svc = top["evidence"], top["suspected_component"]
    out += [f"**Status:** incident detected  \n**Suspected root cause:** `{svc}` (edge `{top['edge']}`)", "", "## Summary", "",
            f"- p99 latency on `{top['edge']}`: **{_ms(e['p99_ms'])}** ({1+e['p99_lift']:.1f}x baseline)",
            f"- Error rate: **{e['error_rate']*100:.1f}%**; mean retries per call: **{e['retry_mean']:.2f}**",
            f"- Degradation began in window {top['onset_window']}" + (f" (about {top['onset_window']*window_s:.0f}s after the first span)" if window_s else "")]
    if detected_at_s is not None: out.append(f"- Detected {detected_at_s:.0f}s into the run")
    out += ["", "## Ranked suspects", "", "| # | Edge | Score | p99 | Errors |", "|---|---|---|---|---|"]
    out += [f"| {i} | `{r['edge']}` | {r['score']:.0f} | {_ms(r['evidence']['p99_ms'])} | {r['evidence']['error_rate']*100:.1f}% |"
            for i, r in enumerate([r for r in rank if r["score"] >= threshold][:5], 1)]
    out += ["", "Callers of a failing service also look degraded, so the lowest edge with the earliest onset and the largest lift is the likeliest root.",
            "", "## Impact (blast radius)", ""]
    br = data.get("blast_radius", [])
    out += (["| Service | Hops from root | Share of traffic |", "|---|---|---|"] +
            [f"| `{b['application']}` | {b['hops']} | {b['traffic_weight']*100:.0f}% |" for b in br]) if br else ["No affected services found."]
    alerts = [k for k, v in data.get("slo_alerts", {}).items() if v]
    out += ["", "## SLO burn alerts (99% availability, 14.4x fast burn)", "", ", ".join(f"`{a}`" for a in alerts) if alerts else "None firing."]
    out += ["", "## Recommended next steps", ""] + [f"1. {s}" for s in _next_steps(e, svc)]
    if injected:
        hit = injected["service"] == svc
        out += ["", "## Validation (demo only)", "",
                f"Injected: `{injected['mode']}` into `{injected['service']}` at {injected.get('at_s', '?')}s. "
                f"Analyzer {'agreed' if hit else 'DISAGREED'}"
                + (f"; detected {detected_at_s - injected['at_s']:.0f}s after injection." if hit and detected_at_s is not None else ".")]
    return "\n".join(out) + "\n"
