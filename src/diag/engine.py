from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from statistics import median
from .model import Span, Edge

WINDOW_MS = 60_000

def percentile(xs: list[float], p: float) -> float:
    """Nearest-rank percentile over values reconstructed from raw spans."""
    if not xs: return 0.0
    s = sorted(xs); return s[min(len(s)-1, max(0, int((len(s)-1)*p)))]

@dataclass
class EdgeMetrics:
    calls: int; errors: int; error_rate: float; p50_ms: float; p95_ms: float; p99_ms: float

def dependency_graph(spans: list[Span]) -> set[Edge]:
    return {Edge(s.service, s.peer) for s in spans if s.peer and s.peer != s.service}

def edge_metrics(spans: list[Span]) -> dict[str, EdgeMetrics]:
    groups: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        if s.peer and s.peer != s.service: groups[f"{s.service}->{s.peer}"].append(s)
    out = {}
    for k, ss in groups.items():
        ds = [s.duration_ms for s in ss]; errors = sum(s.failed for s in ss)
        out[k] = EdgeMetrics(len(ss), errors, errors/len(ss), percentile(ds,.50), percentile(ds,.95), percentile(ds,.99))
    return out

def per_window(spans: list[Span]) -> dict[int, dict[str, EdgeMetrics]]:
    buckets: dict[int, list[Span]] = defaultdict(list)
    for s in spans: buckets[s.start_ms // WINDOW_MS * WINDOW_MS].append(s)
    return {t: edge_metrics(v) for t,v in sorted(buckets.items())}

def cusum_change(values: list[float], threshold: float = 0.03) -> int | None:
    """One-sided deterministic CUSUM. Returns first anomalous window index."""
    if len(values) < 4: return None
    base = median(values[:max(3, len(values)//3)])
    mad = median([abs(x-base) for x in values[:max(3, len(values)//3)]]) or .001
    acc = 0.0
    for i, x in enumerate(values):
        acc = max(0.0, acc + (x-base) - mad)
        if i >= 3 and acc > threshold: return i
    return None

def burn_alert(error_rates: list[float], objective: float=.99) -> bool:
    """Google SRE-style fast burn: 5m/1h both must burn >=14.4x."""
    budget = 1-objective
    def mean(v): return sum(v)/len(v) if v else 0
    return mean(error_rates[-5:])/budget >= 14.4 and mean(error_rates[-60:])/budget >= 14.4

def rank_root_causes(spans: list[Span]) -> list[dict]:
    """No ML/LLM: rank by failure onset, error, retry amplification, and upstream graph position."""
    graph = dependency_graph(spans); metrics = edge_metrics(spans); windows = per_window(spans)
    nodes = {e.source for e in graph} | {e.target for e in graph}
    incoming = {n: 0 for n in nodes}
    for e in graph: incoming[e.target] += 1
    candidates=[]
    for edge, m in metrics.items():
        series=[wm.get(edge, EdgeMetrics(0,0,0,0,0,0)) for wm in windows.values()]
        rates=[x.error_rate for x in series]
        p99s=[x.p99_ms for x in series]
        error_onset=cusum_change(rates)
        latency_onset=cusum_change(p99s, threshold=20.0)
        onset=min(x for x in (error_onset, latency_onset) if x is not None) if (error_onset is not None or latency_onset is not None) else None
        if onset is None: continue
        es=[s for s in spans if s.peer and f"{s.service}->{s.peer}" == edge]
        retry=sum(s.retries for s in es)/len(es)
        baseline=median(p99s[:max(3,len(p99s)//3)]) or 1.0
        latency_lift=max(0.0, m.p99_ms/baseline-1.0)
        # earlier onset wins; position favours failures with many callers.
        target=edge.split("->",1)[1]
        score=100*m.error_rate + 10*retry + 8*latency_lift + 3*incoming[target] + (len(rates)-onset)/max(1,len(rates))
        candidates.append({"edge":edge,"suspected_component":target,"score":round(score,4),"onset_window":onset,"evidence":{"error_rate":m.error_rate,"retry_mean":retry,"p99_ms":m.p99_ms,"p99_lift":round(latency_lift,3)}})
    return sorted(candidates, key=lambda x:(-x["score"], x["edge"]))

def blast_radius(spans: list[Span], root: str) -> list[dict]:
    """Downstream affected apps weighted by observed request count, not topology alone."""
    graph=dependency_graph(spans); adj: dict[str,set[str]]=defaultdict(set)
    for e in graph: adj[e.source].add(e.target)
    traffic=defaultdict(int)
    for s in spans:
        if s.peer: traffic[s.service]+=1
    q=deque([(root,0)]); seen={root}; result=[]
    while q:
        n,d=q.popleft()
        for nxt in sorted(adj[n]):
            if nxt not in seen: seen.add(nxt); q.append((nxt,d+1))
        if n != root: result.append({"application":n,"hops":d,"observed_calls":traffic[n],"traffic_weight":traffic[n]/max(1,sum(traffic.values()))})
    # affected callers also matter: find services with paths into root
    callers=defaultdict(set)
    for e in graph: callers[e.target].add(e.source)
    q=deque([(root,0)])
    while q:
        n,d=q.popleft()
        for prev in sorted(callers[n]):
            if prev not in seen: seen.add(prev); q.append((prev,d+1)); result.append({"application":prev,"hops":d+1,"observed_calls":traffic[prev],"traffic_weight":traffic[prev]/max(1,sum(traffic.values()))})
    return sorted(result,key=lambda x:(-x["traffic_weight"],x["application"]))

def report(spans: list[Span]) -> dict:
    wm=per_window(spans); ranks=rank_root_causes(spans); root=ranks[0]["suspected_component"] if ranks else None
    by_edge={k:[v.get(k,EdgeMetrics(0,0,0,0,0,0)).error_rate for v in wm.values()] for k in edge_metrics(spans)}
    return {"graph":sorted(e.key() for e in dependency_graph(spans)),"edge_metrics":{k:asdict(v) for k,v in edge_metrics(spans).items()},"slo_alerts":{k:burn_alert(v) for k,v in by_edge.items()},"ranking":ranks,"blast_radius":blast_radius(spans,root) if root else []}
