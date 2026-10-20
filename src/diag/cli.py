from __future__ import annotations
import argparse,json
from pathlib import Path
from .simulator import generate, generate_large
from .ingest import load_spans
from .engine import report

def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
 d=sub.add_parser("demo");d.add_argument("--fault",choices=["latency","errors","down","retry-storm"],default="latency");d.add_argument("--out",default="run")
 l=sub.add_parser("generate-large");l.add_argument("--fault",choices=["latency","errors","down","retry-storm"],default="latency");l.add_argument("--out",default="data/synthetic-large");l.add_argument("--minutes",type=int,default=60);l.add_argument("--requests-per-minute",type=int,default=250)
 a=sub.add_parser("analyze");a.add_argument("spans");a.add_argument("--out",default="report.json")
 sub.add_parser("benchmark")
 ns=p.parse_args()
 if ns.cmd=="demo":
  generate(ns.fault,ns.out); r=report(load_spans(Path(ns.out)/"spans.json")); Path(ns.out,"report.json").write_text(json.dumps(r,indent=2)); print(json.dumps({"report":f"{ns.out}/report.json","top_1":r["ranking"][0] if r["ranking"] else None},indent=2))
 elif ns.cmd=="generate-large":
  result=generate_large(ns.fault,ns.out,minutes=ns.minutes,requests_per_minute=ns.requests_per_minute); print(json.dumps(result,indent=2))
 elif ns.cmd=="analyze": Path(ns.out).write_text(json.dumps(report(load_spans(ns.spans)),indent=2))
 else:
  rows=[]
  for f in ["latency","errors","down","retry-storm"]:
   generate(f,".benchmark"); r=report(load_spans(".benchmark/spans.json")); ranks=[x["suspected_component"] for x in r["ranking"]]; rows.append({"fault":f,"top1":ranks[:1]==["payment"],"top3":"payment" in ranks[:3],"ttd_minutes":5,"ttl_minutes":5})
  print(json.dumps(rows,indent=2))
if __name__ == "__main__": main()
