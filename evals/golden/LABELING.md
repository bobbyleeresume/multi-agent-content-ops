# Golden Set: Dataset & Labeling Process

This document describes where `evals/golden/*.json` comes from, what each
label means, and how to add to it. It is documentation, not a fixture — the
eval harness (`evals/run_evals.py::eval_gate_behavior`) globs `*.json` in
this directory, which already excludes this file.

## Dataset

All five fixtures are **hand-authored synthetic data** — invented game
titles and ids for this portfolio project. None of it comes from a real
game catalog, a real RAWG API response, or any production system. Each
fixture is a small, deliberately minimal layout constructed to exercise one
specific gate outcome.

| Fixture | Tier | Rows | Intent |
|---------|------|------|--------|
| `good_layout.json` | standard | Top Picks, Indie Spotlight | Everything valid — all gates pass |
| `bad_layout.json` | casual | Top Picks (incl. an AO title) | G02 violation: AO is never allowed, any tier |
| `bad_layout_missing_field.json` | standard | Top Picks | G01 violation: one title has an empty `rating` |
| `bad_layout_row_size.json` | standard | Top Picks (2 titles) | G03 violation: below the row-size minimum |
| `bad_layout_duplicate.json` | standard | Top Picks (dup id) | G04 violation: the same `id` appears twice in one row |

## Label Schema

Each fixture is a JSON object:

| Field | Type | Meaning |
|-------|------|---------|
| `tier` | string | Tier passed to `ValidationAgent` (`premium` / `standard` / `casual`) |
| `rows` | object | `{row_name: [title, ...]}`, the same shape the pipeline produces |
| `expect_passed` | bool | Whether `ValidationReport.passed` must be `True` |
| `expect_failed_gate` | string \| absent | Only checked when `expect_passed` is `false`. Must equal the `gate` name of the **first** gate that fails |

`expect_failed_gate` encodes fail-fast order, not just "some gate fails."
Gates run in a fixed sequence (G01 → G02 → G03 → G04) and stop at the first
failure (`gates/validation_gates.py::run_all`), so a fixture with more than
one violation is only useful if you know — and assert — which one fires
first. Every "bad" fixture in this set is built to have exactly one kind of
violation, precisely so `expect_failed_gate` is unambiguous.

## Coverage Matrix

| Fixture | G01 | G02 | G03 | G04 |
|---------|:---:|:---:|:---:|:---:|
| `good_layout.json` | pass | pass | pass | pass |
| `bad_layout.json` | pass | **FAIL** | — | — |
| `bad_layout_missing_field.json` | **FAIL** | — | — | — |
| `bad_layout_row_size.json` | pass | pass | **FAIL** | — |
| `bad_layout_duplicate.json` | pass | pass | pass | **FAIL** |

("—" = never reached, because fail-fast stopped the run at an earlier gate.)
As of this set, all four gates have at least one fixture that fails on them
first, plus the one fixture that passes all four.

## Labeling Procedure

There is a single maintainer on this project; there is no independent
second-reviewer step today. The procedure below is what actually happens,
not an aspirational process:

1. **Decide the target.** Pick which gate the new fixture should fail first
   (or that it should pass everything).
2. **Construct the minimal layout.** Write the smallest `rows` object that
   trips the target gate and nothing earlier in fail-fast order — e.g. a
   G03 fixture must still have valid required fields and a valid rating for
   its tier, or G01/G02 would fire first instead.
3. **Verify the label by actually running the gates**, not by inspection —
   e.g.:
   ```
   python3 -c "
   from agents.validation_agent import ValidationAgent
   import json
   data = json.load(open('evals/golden/<new_fixture>.json'))
   r = ValidationAgent().run({'rows': data['rows'], 'tier': data['tier']})
   print(r.passed, [x.gate for x in r.results if not x.passed])
   "
   ```
   Set `expect_passed` / `expect_failed_gate` from what this actually
   prints, not from what was intended — the two can diverge (e.g. an
   off-by-one in row count, or a rating that's valid for the wrong tier).
4. **Review.** The maintainer re-reads the fixture and the gate output
   together before committing. No second person signs off; this is the
   honest current state, not a target process.
5. **Run the full eval suite** (`python3 evals/run_evals.py`) to confirm the
   new fixture is picked up by the `*.json` glob and passes alongside the
   existing set.

## Versioning

Fixtures are plain files under version control — every addition or edit is
a normal commit, so `git log --follow evals/golden/<fixture>.json` is the
change history. There is no separate fixture-versioning scheme beyond git.
`eval_gate_behavior` runs in CI (`.github/workflows/tests.yml`) on every
push and PR, so a fixture edit that changes the expected verdict without a
matching code change fails the build — this is what "blocks regressions"
means in practice for this dataset.
