# REFACTOR — Audit Findings & Plan (2026-07-17)

A code audit against the README's claims and the original design goals. Each
finding was verified against the current source (see file references). Ordered
plan at the bottom; items land as independent commits.

## Findings

### F1 — Documentation drift: described features that are not implemented

| Claim | Reality |
|-------|---------|
| README / `agents/curation_agent.py` docstring: "LLM enriches row descriptions" | CurationAgent makes **no LLM call**. The only LLM call sites in the pipeline are `agents/comms_agent.py:34` and the optional eval judge (`evals/run_evals.py:89`). |
| README: "CurationAgent … writes layout to KB state"; "CommsAgent reads final state from KB" | Nothing ever writes `kb/state/current_layout.json` (still its seeded-empty content). CommsAgent reads rows from the orchestrator context, not from KB state. |
| `kb/domain/row_rules.md` Rotation Policy (bi-weekly refresh, 2-week Top Picks cooldown) | Not implemented anywhere. |

Docs must describe what the code does. Fix by aligning the README/docstrings
(and moving Rotation Policy to the roadmap), not by hastily implementing
features to match prose.

### F2 — The one production-path LLM call restates deterministic data

`CommsAgent._narrative` sends six deterministic fields (week, tier, region,
row count, title count, publish status) to the LLM and asks for prose. The
offline fallback template conveys the identical information. The
`count_faithful` eval exists to police a hallucination risk this call itself
introduces. An LLM surface should do generative work or not exist.

### F3 — A deterministic validator carries LLM capability

`ValidationAgent` inherits `BaseAgent` but uses only `read_kb`; `llm()` /
`safe_json()` sit unused on the class. There is no forced API key (offline
fallback works), but determinism is guaranteed by convention, not by
construction — nothing stops a future edit from calling the LLM inside a gate
path. Capability should be split so the validator cannot reach an LLM by type.

### F4 — Policy loading: silent fallback and partial KB coverage

- `ValidationAgent._rating_policy` and `CurationAgent._row_set` regex-parse KB
  markdown and **silently** fall back to code defaults when the file is missing
  or the table format changes — a KB policy edit can silently fail to take
  effect. Policy loading must be loud (warn or fail, configurable).
- Required fields (G01) and row size bounds (G03) are documented in the KB but
  actually sourced from code constants (`gates/validation_gates.py:25-27`);
  the KB copy is decorative. The README's "rules live in the KB, not in code"
  currently holds only for the rating policy and row set.

### F5 — Untyped payloads; vocabulary mismatch surfaces only at gates (or never)

Rows travel as `dict[str, list[dict]]` end to end. Concrete latent bug: the
RAWG path emits ESRB **full names** ("Everyone", "Teen", "Mature") from the
API (`tools/game_catalog.py:44`), while the CSV, gates, and policy all use
**codes** ("E", "T", "M"). With a live `RAWG_API_KEY`, G02 flags every rated
title as a violation. There is no normalization or type validation at the
catalog boundary, so the mismatch is invisible offline and explodes at the
gate — the exact failure mode typed objects exist to prevent.

## Plan

| # | Item | Fixes | Size | Status |
|---|------|-------|------|--------|
| R1 | **Honest docs** — align README/docstrings with the implementation; move Rotation Policy to roadmap; delete or wire up `kb/state/current_layout.json` | F1 | S | ✅ 2026-07-17 |
| R2 | **Typed domain objects** — `Title` dataclass + `Rating` enum with construction-time validation; normalize ESRB names → codes at the `game_catalog` boundary; typed at the curation boundary; the downstream contract stays JSON-serializable dicts; gates re-check as defense in depth | F5 | M | ✅ 2026-07-17 |
| R3 | **Loud policy loader** — single `PolicyLoader` that parses rating policy, required fields, and row-size bounds from the KB; missing file / failed parse warns loudly (or fails, configurable); code defaults demoted to clearly-labeled emergency fallback | F4 | M | — |
| R4 | **Capability split** — `BaseAgent` → KB-grounding base + LLM-capable subclass; `ValidationAgent` gets the KB base only, making validator determinism structural | F3 | S | ✅ 2026-07-17 |
| R5 | **CommsAgent LLM surface (decision)** — either (a) drop the LLM call and declare the report deterministic, or (b) make it generative: a week-over-week change narrative diffing the current layout against the previously published one (`tools/mock_publish.read_published`). Recommendation: **(b)** — it gives the guardrails/evals a real job. | F2 | M | — |
| R6 | **Tests/evals track the above** — typed-boundary tests (ESRB normalization), loud-loader tests, CI stays green offline | all | S | — |

Order: R1 → R2 → R3 → R4 → R5 → R6 (R6 lands alongside each item).

## Out of scope (tracked elsewhere)

Telemetry cost partitioning by stage/purpose, versioned pricing records, and
eval dataset labeling docs (`evals/golden/LABELING.md`) are a separate
reliability-layer work stream — see `PLAN.md` roadmap.
