"""Raw OpenTelemetry JSON and proxy-log ingestion; intentionally no metric input."""
from __future__ import annotations
import json
from pathlib import Path
from .model import Span

def load_spans(path: str | Path) -> list[Span]:
    records = json.loads(Path(path).read_text())
    out = []
    for r in records:
        # Native demo format plus an OTLP-shaped subset.
        attrs = r.get("attributes", {})
        out.append(Span(
            trace_id=r.get("trace_id") or r.get("traceId"), span_id=r.get("span_id") or r.get("spanId"),
            parent_id=r.get("parent_id") or r.get("parentSpanId"),
            service=r.get("service") or attrs.get("service.name"),
            peer=r.get("peer") or attrs.get("peer.service") or attrs.get("server.address"),
            start_ms=int(r.get("start_ms", r.get("startTimeUnixNano", 0) // 1_000_000)),
            duration_ms=float(r.get("duration_ms", r.get("endTimeUnixNano", 0) / 1_000_000 - r.get("startTimeUnixNano", 0) / 1_000_000)),
            status=r.get("status", r.get("status_code", "OK")), retries=int(r.get("retries", 0))))
    return out

def load_proxy_logs(path: str | Path) -> list[dict]:
    """JSON-lines Envoy/Nginx access logs, retained as corroborating raw evidence."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
