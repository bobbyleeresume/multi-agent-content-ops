# ADR-001: Fail-fast validation gates block publish

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

The pipeline publishes to a live surface. Bad rows (missing fields, disallowed
ratings, duplicates) must never reach production, and a human should not have to
spot-check every build.

## Decision

Run G01–G04 as ordered, fail-fast gates. The first failing gate halts the
pipeline before PUBLISH and emits a violation report. Publish only runs when
every gate passes.

## Consequences

- No human spot-check required on the critical path.
- Rules live in the KB (`content_policy.md`, `row_rules.md`), not in code, so
  policy changes need no deploy.
- Trade-off: fail-fast reports only the first failing gate. A future change
  could run all gates and aggregate violations for faster batch fixing.
