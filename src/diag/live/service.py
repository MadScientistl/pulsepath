"""One real HTTP microservice per OS process.

    python -m diag.live.service <name> <collector-url>

Each service does small amounts of genuine work (stock accounting, an append-only ledger,
a rule-based fraud score), calls its downstream peers over real HTTP, and reports a client
span per outbound call plus a server access-log line to the collector. Fault injection
arrives through POST /admin/fault, exactly like a chaos proxy would toggle it.
"""
from __future__ import annotations
import hashlib, json, random, sys, threading, time, urllib.error, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .topology import SERVICES, url_of

class Telemetry:
    def __init__(self, collector_url: str):
        self.url, self.spans, self.logs, self.lock = collector_url, [], [], threading.Lock()
        threading.Thread(target=self._flush_loop, daemon=True).start()
    def span(self, **kw):
        with self.lock: self.spans.append(kw)
    def log(self, **kw):
        with self.lock: self.logs.append(kw)
    def _flush_loop(self):
        while True:
            time.sleep(.4)
            with self.lock: spans, logs, self.spans, self.logs = self.spans, self.logs, [], []
            if not (spans or logs): continue
            try:
                req = urllib.request.Request(self.url, json.dumps({"spans": spans, "logs": logs}).encode(),
                                             {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2).read()
            except Exception: pass

class Ctx:
    """Per-request context: carries the trace and makes traced downstream calls."""
    def __init__(self, svc: "Service", trace_id: str, parent_id):
        self.svc, self.trace_id, self.parent_id = svc, trace_id, parent_id
    def call(self, peer: str, path: str, timeout: float = 3.0):
        retries = self.svc.calls[peer]
        span_id = uuid.uuid4().hex[:16]
        start = time.time(); status, body, attempts = 0, {}, 0
        for attempts in range(retries + 1):
            req = urllib.request.Request(url_of(peer) + path, headers={"X-Trace-Id": self.trace_id, "X-Parent-Span": span_id})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r: status, body = r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e: status = e.code
            except Exception: status = 0   # refused / timed out: the peer is unreachable
            if status == 200: break
            if attempts < retries: time.sleep(.05 * (attempts + 1))
        self.svc.tel.span(trace_id=self.trace_id, span_id=span_id, parent_id=self.parent_id, service=self.svc.name, peer=peer,
                          start_ms=int(start * 1000), duration_ms=round((time.time() - start) * 1000, 2),
                          status="OK" if status == 200 else "ERROR", retries=attempts)
        return status, body

def pause(lo_ms: float, hi_ms: float): time.sleep(random.uniform(lo_ms, hi_ms) / 1000)

class Service:
    def __init__(self, name: str, collector_url: str):
        self.name, self.calls, self.tel = name, SERVICES[name]["calls"], Telemetry(collector_url)
        self.fault, self.lock, self.state = {"mode": "none"}, threading.Lock(), {}
        if name == "inventory": self.state["stock"] = {f"sku-{i}": 500 for i in range(20)}
        if name == "ledger": self.state["entries"] = []
        if name == "payment": self.state["seen"] = {}
        if name == "product-db": self.state["rows"] = {f"sku-{i}": {"sku": f"sku-{i}", "price": 5 + i} for i in range(20)}

    def apply_fault(self):
        """Returns an HTTP status to short-circuit with, or None. Latency faults sleep first."""
        mode = self.fault["mode"]
        if mode == "latency": time.sleep(.35 + random.expovariate(1 / .12))
        elif mode == "errors" and random.random() < .35: return 500
        elif mode == "retry-storm":
            pause(60, 120)
            if random.random() < .6: return 503
        return None

    def handle(self, path: str, ctx: Ctx):
        n = self.name
        if n == "frontend":
            st, body = ctx.call("catalog", "/products") if path.startswith("/browse") else ctx.call("checkout", "/checkout")
            return (200, body) if st == 200 else (502, {"error": "upstream"})
        if n == "catalog":
            pause(3, 8); st, body = ctx.call("product-db", "/query")
            return (200, {"items": body.get("rows", [])}) if st == 200 else (502, {})
        if n == "product-db": pause(2, 6); return 200, {"rows": random.sample(list(self.state["rows"].values()), 5)}
        if n == "checkout":
            sku = f"sku-{random.randrange(20)}"
            for peer, p in (("inventory", f"/reserve?sku={sku}"), ("payment", f"/charge?amount={random.randrange(5, 200)}"), ("shipping", "/quote")):
                if ctx.call(peer, p)[0] != 200: return 502, {"failed_at": peer}
            return 200, {"order": uuid.uuid4().hex[:8]}
        if n == "inventory":
            pause(3, 8); sku = path.split("sku=")[-1]
            with self.lock:
                if self.state["stock"].get(sku, 0) <= 0: self.state["stock"][sku] = 500
                self.state["stock"][sku] -= 1; left = self.state["stock"][sku]
            return 200, {"sku": sku, "left": left}
        if n == "payment":
            amount = int(path.split("amount=")[-1]); st, body = ctx.call("fraud", f"/score?amount={amount}")
            if st != 200 or body.get("score", 1) > .95: return 502, {}
            pause(8, 18); txn = uuid.uuid4().hex[:10]
            with self.lock: self.state["seen"][txn] = amount
            st, _ = ctx.call("ledger", f"/append?txn={txn}&amount={amount}")
            return (200, {"txn": txn}) if st == 200 else (502, {})
        if n == "fraud":
            pause(4, 10); h = int(hashlib.sha1(path.encode() + uuid.uuid4().bytes).hexdigest()[:4], 16) / 65535
            return 200, {"score": round(h * .9, 3)}
        if n == "ledger":
            pause(2, 6)
            with self.lock: self.state["entries"].append(path); size = len(self.state["entries"])
            return 200, {"entries": size}
        if n == "shipping": pause(5, 12); return 200, {"eta_days": random.randint(2, 6)}
        return 404, {}

def make_handler(svc: Service):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            if self.path == "/admin/fault":
                svc.fault = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"); self._send(200, svc.fault)
            else: self._send(404, {})
        def do_GET(self):
            if self.path == "/healthz": return self._send(200, {"service": svc.name, "fault": svc.fault["mode"]})
            trace = self.headers.get("X-Trace-Id", uuid.uuid4().hex); parent = self.headers.get("X-Parent-Span")
            start = time.time(); code = svc.apply_fault()
            code, body = (code, {"error": "injected"}) if code else svc.handle(self.path, Ctx(svc, trace, parent))
            self._send(code, body)
            svc.tel.log(timestamp=int(start * 1000), service=svc.name, path=self.path.split("?")[0], status=code,
                        duration_ms=round((time.time() - start) * 1000, 2), trace_id=trace)
    return H

class Server(ThreadingHTTPServer):
    request_queue_size = 256
    daemon_threads = True

def main():
    name, collector = sys.argv[1], sys.argv[2]
    Server(("127.0.0.1", SERVICES[name]["port"]), make_handler(Service(name, collector))).serve_forever()

if __name__ == "__main__": main()
