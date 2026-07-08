"""
obs/telemetry.py

Lightweight observability: per-stage latency, LLM token usage, and cost per run.
Zero dependencies, works offline (offline runs simply record 0 LLM calls).

Usage:
    from obs.telemetry import get_tracer
    tr = get_tracer(); tr.reset()
    with tr.span("VALIDATE"):
        ...
    tr.record_llm(model, in_tok, out_tok, latency_ms)
    print(tr.summary_text()); tr.flush("obs/trace/run.json")
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

# Claude pricing (USD per 1M tokens). Update as pricing changes.
PRICING = {
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
}


@dataclass
class LLMCall:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


@dataclass
class SpanRecord:
    name: str
    duration_ms: float


@dataclass
class RunTrace:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spans: list[SpanRecord] = field(default_factory=list)
    llm_calls: list[LLMCall] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.llm_calls)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c.cost_usd for c in self.llm_calls), 6)

    @property
    def total_latency_ms(self) -> float:
        return round(sum(s.duration_ms for s in self.spans), 1)


class Tracer:
    def __init__(self) -> None:
        self.trace = RunTrace()

    def reset(self) -> None:
        self.trace = RunTrace()

    @contextmanager
    def span(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dur = (time.perf_counter() - t0) * 1000
            self.trace.spans.append(SpanRecord(name, round(dur, 1)))

    def record_llm(self, model: str, input_tokens: int, output_tokens: int,
                   latency_ms: float) -> None:
        price = PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (input_tokens / 1e6) * price["input"] + (output_tokens / 1e6) * price["output"]
        self.trace.llm_calls.append(
            LLMCall(model, input_tokens, output_tokens, round(latency_ms, 1), round(cost, 6))
        )

    def summary(self) -> dict:
        return {
            "total_latency_ms": self.trace.total_latency_ms,
            "llm_calls": len(self.trace.llm_calls),
            "total_tokens": self.trace.total_tokens,
            "total_cost_usd": self.trace.total_cost_usd,
            "spans": [asdict(s) for s in self.trace.spans],
        }

    def summary_text(self) -> str:
        s = self.summary()
        lines = ["── run telemetry " + "─" * 33]
        for sp in s["spans"]:
            lines.append(f"  {sp['name']:<9} {sp['duration_ms']:>8.1f} ms")
        lines.append(
            f"  TOTAL     {s['total_latency_ms']:>8.1f} ms · "
            f"{s['llm_calls']} LLM call(s) · {s['total_tokens']} tok · "
            f"${s['total_cost_usd']:.6f}"
        )
        lines.append("─" * 50)
        return "\n".join(lines)

    def flush(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"started_at": self.trace.started_at, **self.summary(),
                   "llm_calls_detail": [asdict(c) for c in self.trace.llm_calls]}
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


_TRACER = Tracer()


def get_tracer() -> Tracer:
    return _TRACER
