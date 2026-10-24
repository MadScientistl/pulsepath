"""Orchestrates a live run: spawns the service processes, drives load, collects spans, diagnoses."""
from __future__ import annotations
import json, os, random, subprocess, sys, threading, time, urllib.request, uuid
from collections import defaultdict
from pathlib import Path
from ..engine import report, per_window
from ..model import Span
from .topology import SERVICES, url_of

FAULTS = ("latency", "errors", "down", "retry-storm")
FIELDS = ("trace_id", "span_id", "parent_id", "service", "peer", "start_ms", "duration_ms", "status", "retries")

class Collector:
    """Receives spans/access logs from every service (the role an OTel collector plays)."""
    def __init__(self, out: Path):
        self.out, self.lock = out, threading.Lock(); self.reset()
    def reset(self):
        with self.lock: self.spans, self.logs = [], []
        self.out.mkdir(parents=True, exist_ok=True)
        for f in ("spans.jsonl", "proxy.jsonl"): (self.out / f).write_text("")
    def ingest(self, payload: dict):
        spans, logs = payload.get("spans", []), payload.get("logs", [])
        with self.lock:
            self.spans.extend(spans); self.logs.extend(logs)
            with open(self.out / "spans.jsonl", "a") as f: f.writelines(json.dumps(s) + "\n" for s in spans)
            with open(self.out / "proxy.jsonl", "a") as f: f.writelines(json.dumps(x) + "\n" for x in logs)
    def snapshot(self) -> list[dict]:
        with self.lock: return list(self.spans)

class Cluster:
    def __init__(self, collector_url: str):
        self.url, self.procs = collector_url, {}
        self.src = str(Path(__file__).resolve().parents[2])
    def spawn(self, name: str):
        env = dict(os.environ, PYTHONPATH=self.src)
        self.procs[name] = subprocess.Popen([sys.executable, "-m", "diag.live.service", name, self.url],
                                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def start(self):
        for name in SERVICES: self.spawn(name)
        deadline = time.time() + 10
        while time.time() < deadline and not all(self.health().values()): time.sleep(.2)
    def health(self) -> dict:
        out = {}
        for name in SERVICES:
            try: urllib.request.urlopen(url_of(name) + "/healthz", timeout=.5).read(); out[name] = True
            except Exception: out[name] = False
        return out
    def set_fault(self, name: str, mode: str):
        if mode == "down":                       # a genuinely dead process: connections get refused
            self.procs[name].kill(); self.procs[name].wait(); return
        if self.procs[name].poll() is not None: self.spawn(name); time.sleep(.6)
        req = urllib.request.Request(url_of(name) + "/admin/fault", json.dumps({"mode": mode}).encode())
        urllib.request.urlopen(req, timeout=2).read()
    def stop(self):
        for p in self.procs.values(): p.kill()
        for p in self.procs.values(): p.wait()
        self.procs = {}

class LoadGen:
    """Closed-loop users hitting the public frontend; each request is recorded as a `users` span."""
    def __init__(self, collector: Collector, rps: float = 25, workers: int = 8):
        self.collector, self.rps, self.workers, self.stop_flag, self.threads = collector, rps, workers, threading.Event(), []
    def start(self):
        self.stop_flag.clear()
        self.threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(self.workers)]
        for t in self.threads: t.start()
    def stop(self):
        self.stop_flag.set()
        for t in self.threads: t.join(timeout=4)
    def _worker(self):
        interval = self.workers / self.rps
        while not self.stop_flag.is_set():
            trace, span_id, start = uuid.uuid4().hex, uuid.uuid4().hex[:16], time.time()
            path = "/browse" if random.random() < .6 else "/order"
            try:
                req = urllib.request.Request(url_of("frontend") + path, headers={"X-Trace-Id": trace, "X-Parent-Span": span_id})
                urllib.request.urlopen(req, timeout=5).read(); ok = True
            except Exception: ok = False
            self.collector.ingest({"spans": [dict(trace_id=trace, span_id=span_id, parent_id=None, service="users", peer="frontend",
                start_ms=int(start * 1000), duration_ms=round((time.time() - start) * 1000, 2), status="OK" if ok else "ERROR", retries=0)]})
            self.stop_flag.wait(max(0, interval - (time.time() - start)) * random.uniform(.7, 1.3))

class LiveSession:
    def __init__(self, root: Path, collector_url: str):
        self.collector = Collector(root / "run" / "live")
        self.cluster, self.load = Cluster(collector_url), LoadGen(self.collector)
        self.started = self.injected = None; self.running = False
        self.lock = threading.Lock()
    def start(self, rps: float = 25):
        with self.lock:
            if self.running: return
            self.collector.reset(); self.cluster.start(); self.load.rps = rps; self.load.start()
            self.started, self.injected, self.running = time.time(), None, True
    def stop(self):
        with self.lock:
            if not self.running: return
            self.load.stop(); time.sleep(.6); self.cluster.stop(); self.running = False
    def inject(self, service: str, mode: str):
        if not self.running or service not in SERVICES or mode not in FAULTS: raise ValueError("bad fault request")
        self.cluster.set_fault(service, mode); self.injected = {"service": service, "mode": mode, "at": time.time()}
    def clear(self):
        if not self.running: return
        for name in SERVICES: self.cluster.set_fault(name, "none")
        self.injected = None
    def snapshot(self, window_s: int = 2) -> dict:
        rows = self.collector.snapshot(); spans = [Span(**{k: r.get(k) for k in FIELDS}) for r in rows]
        window_ms = window_s * 1000
        data = report(spans, window_ms)
        t0 = min((s.start_ms for s in spans), default=0)
        series = defaultdict(list)
        for t, edges in list(per_window(spans, window_ms).items())[-45:]:
            for edge, m in edges.items():
                series[edge].append({"t": (t - t0) / 1000, "p99": m.p99_ms, "p50": m.p50_ms, "err": m.error_rate, "calls": m.calls})
        data["series"] = series
        data["live"] = {"running": self.running, "elapsed_s": round(time.time() - self.started, 1) if self.started else 0,
                        "spans": len(spans), "window_s": window_s, "health": self.cluster.health() if self.running else {},
                        "injected": ({**self.injected, "at_s": round(self.injected["at"] - self.started, 1)} if self.injected else None),
                        "traces": self._traces(rows)}
        return data
    def _traces(self, rows: list[dict], n: int = 8) -> list[dict]:
        by = defaultdict(list)
        for r in rows[-1500:]: by[r["trace_id"]].append(r)
        done = [v for v in by.values() if any(r["service"] == "users" for r in v)][-n:]
        return [{"trace_id": v[0]["trace_id"][:8], "spans": [{"edge": f"{r['service']}->{r['peer']}", "ms": r["duration_ms"], "status": r["status"], "retries": r["retries"]}
                for r in sorted(v, key=lambda r: r["start_ms"])]} for v in reversed(done)]
