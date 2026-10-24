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
from diag.simulator import generate, generate_large
from diag.live.session import LiveSession
LIVE=LiveSession(ROOT,"http://127.0.0.1:8080/v1/ingest")
SCENARIOS=("latency","errors","down","retry-storm")
_CACHE={}
def payload(name, large=False):
 if name not in SCENARIOS: raise ValueError(f"unknown scenario: {name}")
 key=(name,large)
 if key in _CACHE: return _CACHE[key]
 out=ROOT/"run"/("large-"+name if large else name)
 if large: generate_large(name,str(out),minutes=20,requests_per_minute=100)
 else: generate(name,str(out))
 data=report(load_spans(out/"spans.json"));truth=json.loads((out/"hidden_truth.json").read_text());data["scenario"]={"name":name,"fault_began_minute":truth["began_minute"],"large":large};_CACHE[key]=data;return data
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
 def do_GET(self):
  parsed=urlparse(self.path)
  if parsed.path=="/api/diagnostics":
   q=parse_qs(parsed.query);name=q.get("scenario",["latency"])[0];large=q.get("size",[""])[0]=="large"
   try: body=json.dumps(payload(name,large)).encode();status=HTTPStatus.OK
   except ValueError as e: body=json.dumps({"error":str(e)}).encode();status=HTTPStatus.BAD_REQUEST
   self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body);return
  if parsed.path=="/api/live/report": return self._json(LIVE.snapshot(int(parse_qs(parsed.query).get("window",["2"])[0])))
  return super().do_GET()
 def _json(self,obj,status=HTTPStatus.OK):
  body=json.dumps(obj).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get("Content-Length",0)) or 0);body=json.loads(raw or b"{}");p=urlparse(self.path).path
  try:
   if p=="/v1/ingest": LIVE.collector.ingest(body)
   elif p=="/api/live/start": LIVE.start(float(body.get("rps",25)))
   elif p=="/api/live/stop": LIVE.stop()
   elif p=="/api/live/fault": LIVE.inject(body.get("service"),body.get("mode"))
   elif p=="/api/live/clear": LIVE.clear()
   else: return self._json({"error":"not found"},HTTPStatus.NOT_FOUND)
  except ValueError as e: return self._json({"error":str(e)},HTTPStatus.BAD_REQUEST)
  self._json({"ok":True})
 def log_message(self,*a): pass
if __name__=="__main__":
 print("Dashboard: http://127.0.0.1:8080  (live cluster: /web/live.html)")
 ThreadingHTTPServer.request_queue_size=256
 try: ThreadingHTTPServer(("127.0.0.1",8080),Handler).serve_forever()
 finally: LIVE.stop()
