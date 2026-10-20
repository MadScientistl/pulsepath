from __future__ import annotations
import json, random
from pathlib import Path
from .model import Span

TOPOLOGY=[("frontend","checkout"),("checkout","payment"),("checkout","inventory"),("frontend","catalog")]

# A deliberately heterogeneous e-commerce and platform graph.  It contains
# fan-out, shared platform dependencies, and low-volume background paths so
# graph position and traffic-weighted blast radius have meaningful variation.
LARGE_TOPOLOGY=[
 ("frontend","gateway"),("mobile-api","gateway"),("gateway","checkout"),("gateway","catalog"),
 ("gateway","search"),("checkout","payment"),("checkout","inventory"),("checkout","shipping"),
 ("checkout","tax"),("payment","fraud"),("payment","ledger"),("payment","notification"),
 ("catalog","product-db"),("catalog","recommendation"),("search","search-index"),("search","recommendation"),
 ("inventory","warehouse"),("shipping","carrier"),("shipping","address"),("fraud","risk-model"),
 ("recommendation","profile"),("profile","identity"),("notification","email"),("notification","sms"),
 ("analytics","event-bus"),("event-bus","warehouse"),("support","identity"),("admin","ledger")]
def generate(fault: str, out: str, seed: int=7) -> dict:
    """Emulates OTEL spans/proxy access records from an under-load demo. Hidden label is separate."""
    rng=random.Random(seed); spans=[]; logs=[]; base=1_700_000_000_000
    for minute in range(12):
      for req in range(90):
       trace=f"{minute:02x}{req:030x}"; start=base+minute*60_000+req*500
       for i,(source,target) in enumerate(TOPOLOGY):
        impacted=minute>=5 and ((fault in ("latency","errors","down","retry-storm")) and target=="payment")
        latency=20+rng.expovariate(1/8); status="OK"; retries=0
        if impacted and fault=="latency": latency += 600+rng.expovariate(1/150)
        if impacted and fault in ("errors","down","retry-storm"):
          status="ERROR" if rng.random() < (.95 if fault=="down" else .35) else "OK"
          retries=3 if fault=="retry-storm" else (1 if status=="ERROR" else 0)
          latency += retries*100
        s=Span(trace,f"{trace}{i}",None,source,target,start+i*5,latency,status,retries); spans.append(s)
        logs.append({"timestamp":s.start_ms,"upstream_service":source,"downstream_service":target,"status":503 if status!="OK" else 200,"duration_ms":latency,"trace_id":trace})
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    (p/"spans.json").write_text(json.dumps([s.__dict__ for s in spans]))
    (p/"proxy.jsonl").write_text("\n".join(json.dumps(x) for x in logs)+"\n")
    (p/"hidden_truth.json").write_text(json.dumps({"fault":fault,"root":"payment","began_minute":5}))
    return {"spans":len(spans),"fault":fault}

def generate_large(fault: str, out: str, seed: int=71, minutes: int=60,
                   requests_per_minute: int=250) -> dict:
    """Generate a large raw corpus (default: about 196,000 spans + proxy records).

    This is still span/proxy input, not pre-aggregated metric data. Different
    paths get deterministic traffic weights and the fault identity is emitted
    separately from the analyzer input.
    """
    rng=random.Random(seed); spans=[]; logs=[]; base=1_700_100_000_000
    # Main checkout path receives most traffic, while platform/background
    # paths create realistic sparse edges.
    weights=[12 if a in ("frontend","gateway","checkout") else 5 if a in ("payment","catalog","search") else 2 for a,_ in LARGE_TOPOLOGY]
    for minute in range(minutes):
      for req in range(requests_per_minute):
       trace=f"{minute:04x}{req:028x}"; start=base+minute*60_000+req*max(1,60_000//requests_per_minute)
       for i,(source,target) in enumerate(LARGE_TOPOLOGY):
        # Deterministic sampling of low-volume paths retains sparse topology.
        if rng.randrange(12) >= weights[i]: continue
        impacted=minute>=minutes//2 and target=="payment"
        latency=12+rng.expovariate(1/7); status="OK"; retries=0
        if impacted and fault=="latency": latency+=550+rng.expovariate(1/180)
        if impacted and fault in ("errors","down","retry-storm"):
          status="ERROR" if rng.random() < (.96 if fault=="down" else .32) else "OK"
          retries=4 if fault=="retry-storm" else (1 if status=="ERROR" else 0); latency+=retries*105
        s=Span(trace,f"{trace}{i:02x}",None,source,target,start+i,status and latency,status,retries)
        spans.append(s);logs.append({"timestamp":s.start_ms,"upstream_service":source,"downstream_service":target,"status":503 if status!="OK" else 200,"duration_ms":latency,"trace_id":trace})
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    (p/"spans.json").write_text(json.dumps([s.__dict__ for s in spans]))
    (p/"proxy.jsonl").write_text("\n".join(json.dumps(x) for x in logs)+"\n")
    (p/"hidden_truth.json").write_text(json.dumps({"fault":fault,"root":"payment","began_minute":minutes//2,"topology":"large"}))
    return {"spans":len(spans),"services":len({x for e in LARGE_TOPOLOGY for x in e}),"edges":len(LARGE_TOPOLOGY),"fault":fault}
