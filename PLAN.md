# Build Plan & Roadmap

## Built ✅

| Layer | File | Status |
|-------|------|--------|
| Orchestrator | `orchestrator.py` | ✅ INIT→CURATE→VALIDATE→PUBLISH→REPORT state machine, per-stage tracing |
| Agents | `agents/` (base + curation + validation + comms) | ✅ |
| Gates | `gates/validation_gates.py` | ✅ G01–G04, fail-fast, ValidationReport |
| Tools | `tools/` (mock_publish MCP pattern + game_catalog RAWG/CSV) | ✅ |
| KB | `kb/` (3 domain policies, state JSON, ADR log) | ✅ single source of truth |
| Data | `data/synthetic_games.csv` | ✅ 30 titles, offline fallback |
| **Observability** | `obs/telemetry.py` | ✅ per-stage latency, token usage, cost/run, JSON trace |
| **Evals** | `evals/run_evals.py` + `evals/golden/` | ✅ gate-behavior + comms-quality (deterministic judge) + optional LLM-as-judge |
| **Guardrails** | `guardrails.py` | ✅ PII redaction + blocklist on free-text output |
| **Failure modes** | `agents/base.py::safe_json` | ✅ schema-guarded JSON parse w/ retry + graceful None |
| Tests | `tests/test_gates.py`, `tests/test_extras.py` | ✅ 13 + 6 |
| Docs | `README.md` | ✅ Mermaid diagram, quickstart, example output |
| CI | `.github/workflows/tests.yml` | ✅ gate tests + extras + evals + dry-run smoke |

## Roadmap (next)

1. **Model routing** — route between Haiku (cheap enrichment) and a larger model
   (harder reasoning) with a cost/quality policy; telemetry already tracks the
   per-model cost needed to drive this.
2. **Eval expansion** — grow the golden set, add adversarial layouts, and track
   an eval score trend over time (regression budget in CI).
3. **Retrieval upgrade** — the KB is currently structured file lookup (not vector
   retrieval). If the KB grows, add embeddings + hybrid retrieval — and only
   then call it RAG.
4. **Structured curation output** — have CurationAgent emit JSON via `safe_json`
   so row descriptions are validated against a schema, not free text.
