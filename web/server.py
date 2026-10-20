"""Local dashboard server backed by the deterministic diagnostics engine."""
from __future__ import annotations
import json, sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from diag.engine import report
from diag.ingest import load_spans
from diag.simulator import generate
SCENARIOS=("latency","errors","down","retry-storm")
def payload(name):
 if name not in SCENARIOS: raise ValueError(f"unknown scenario: {name}")
 out=ROOT/"run"/name;generate(name,str(out));data=report(load_spans(out/"spans.json"));truth=json.loads((out/"hidden_truth.json").read_text());data["scenario"]={"name":name,"fault_began_minute":truth["began_minute"]};return data
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
 def do_GET(self):
  parsed=urlparse(self.path)
  if parsed.path=="/api/diagnostics":
   try: body=json.dumps(payload(parse_qs(parsed.query).get("scenario",["latency"])[0])).encode();status=HTTPStatus.OK
   except ValueError as e: body=json.dumps({"error":str(e)}).encode();status=HTTPStatus.BAD_REQUEST
   self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body);return
  return super().do_GET()
if __name__=="__main__":
 print("Dashboard: http://127.0.0.1:8080");ThreadingHTTPServer(("127.0.0.1",8080),Handler).serve_forever()
