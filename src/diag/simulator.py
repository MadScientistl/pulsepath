from __future__ import annotations
import json, random
from pathlib import Path
from .model import Span

TOPOLOGY=[("frontend","checkout"),("checkout","payment"),("checkout","inventory"),("frontend","catalog")]
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
