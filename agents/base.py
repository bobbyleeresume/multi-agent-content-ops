"""
agents/base.py

BaseAgent — shared scaffolding for every domain agent.

Responsibilities:
  * Read grounding facts from the KB (single source of truth). Agents NEVER
    invent domain state; they read policy/rules from kb/ at runtime.
  * Provide a guarded LLM call with retry + graceful offline fallback so the
    pipeline (and CI) still runs deterministically without an API key.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from obs.telemetry import get_tracer

KB_ROOT = Path(__file__).resolve().parent.parent / "kb"


class BaseAgent:
    name = "BaseAgent"

    # --- KB grounding -----------------------------------------------------------
    def read_kb(self, relpath: str) -> str:
        """Read a KB document as the single source of truth."""
        path = KB_ROOT / relpath
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # --- Guarded LLM call -------------------------------------------------------
    def llm(self, system: str, user: str, max_tokens: int = 512,
            model: str = "claude-3-5-haiku-20241022", retries: int = 2) -> str:
        """Call Claude with retry/backoff. Falls back to '' when no API key,
        so curation/comms degrade to deterministic behavior offline."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return ""  # offline fallback — caller handles empty string
        try:
            from anthropic import Anthropic
        except ImportError:
            return ""
        client = Anthropic(api_key=api_key)
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                t0 = time.perf_counter()
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                latency_ms = (time.perf_counter() - t0) * 1000
                usage = getattr(resp, "usage", None)
                get_tracer().record_llm(
                    model=model,
                    input_tokens=getattr(usage, "input_tokens", 0) or 0,
                    output_tokens=getattr(usage, "output_tokens", 0) or 0,
                    latency_ms=latency_ms,
                )
                return resp.content[0].text
            except Exception as e:  # noqa: BLE001 — retry any transient API error
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        print(f"[{self.name}] LLM unavailable after {retries + 1} tries: {last_err}")
        return ""

    # --- Failure-mode handling for JSON responses -------------------------------
    def safe_json(self, system: str, user: str, required_keys: tuple[str, ...] = (),
                  max_tokens: int = 512, retries: int = 2) -> dict | None:
        """Call the LLM expecting JSON. Strips code fences, validates required
        keys, and retries on malformed output. Returns None if never valid —
        callers fall back to deterministic behavior."""
        for _ in range(retries + 1):
            raw = self.llm(system, user, max_tokens=max_tokens, retries=0)
            if not raw:
                return None
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].removeprefix("json").strip()
            try:
                data = json.loads(cleaned)
            except (ValueError, IndexError):
                continue
            if all(k in data for k in required_keys):
                return data
        return None

    def run(self, context: dict) -> object:  # pragma: no cover - interface
        raise NotImplementedError
