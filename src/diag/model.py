from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    service: str
    peer: str | None
    start_ms: int
    duration_ms: float
    status: str = "OK"
    retries: int = 0

    @property
    def failed(self) -> bool: return self.status != "OK"

@dataclass(frozen=True)
class Edge:
    source: str
    target: str

    def key(self) -> str: return f"{self.source}->{self.target}"
