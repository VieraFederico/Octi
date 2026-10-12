# DECISIONS — Spec 03 Evaluation, docs and bonus

Append-only. Project-wide decisions live in the root `DECISIONS.md` (D-106 … D-112, D-118).

## S03-D-001: Iteration 2's questions and scoring before Iteration 1 (Iteration 2a)

- **Context:** The start gate failed: spec 01 is committed through Iteration 6 and spec 02 through
  Iteration 1. Iteration 1 needs spec 02's graph and `ui/analysis.py` (spec 02 Iterations 3–4), and
  `scripts/run_eval.py` needs `run_analysis` (spec 02 Iteration 3) with `confirm_tables`.
- **Decision (student):** build now only the parts with no dependency on unbuilt code:
  `eval/questions.yaml`, `eval/scoring.py` and their smoke tests ("Iteration 2a"). `run_eval.py`
  ("Iteration 2b") waits for spec 02 Iteration 3; Iteration 1 waits for spec 02 Iteration 4.
- **Rejected:** all of Iteration 2 now (`run_eval.py` against a module that does not exist yet);
  questions only; waiting.
- **Consequences:** the plan's order changes (2a → 1 → 2b → 3). The evaluators read spec 02 §7's
  state field names (`answer_status`, `part_outcomes`, `selection`, `candidates`, `code_attempts`);
  if spec 02's implementation renames one, `eval/scoring.py` follows it.

## S03-D-002: PyYAML pinned as a direct dependency (Iteration 2a)

- **Context:** `eval/questions.yaml` (FR-301) needs a YAML parser; PyYAML 6.0.3 is already in the
  venv through `langchain-core`.
- **Decision:** pin `PyYAML==6.0.3` in `requirements.txt`; read with `yaml.safe_load` only.
- **Rejected:** relying on the transitive install (breaks silently if `langchain-core` drops it);
  JSON instead of YAML (the spec names YAML).
- **Consequences:** nothing to install; the version matches what the student already has.

## S03-D-003: Provisional Table names in `expected_tables` (Iteration 2a) — needs the student

- **Context:** FR-308 matches `expected_tables` by Table name, but names are written by the
  ingestion LLM, not by the sample-PDF constants. A-302 says spec 01's `CONTEXT.md` lists the
  extracted names; it lists only table numbers and pages.
- **Decision (provisional):** use the PDF captions' titles ("Income summary", "Monthly net sales",
  …). Before the live run, the student checks the real names in the Library and the YAML is updated.
- **Rejected:** none yet; open options for the student and the spec tab in the record.
- **Consequences:** `tables_correct` may report ✗ for a correct selection until the names match.

## S03-D-004: The `eval` tag through a `run_analysis` argument (before Iteration 1)

- **Context:** FR-307 needs every evaluation run tagged `eval` inside an `octi-eval` experiment;
  spec 02's `run_analysis` opens its own root trace with fixed tags `["analysis"]`.
- **Decision (student):** Iteration 1 adds an optional `extra_tags` argument to `run_analysis`
  next to `confirm_tables` (one spec 02 edit, reported to the spec tab); Iteration 2b's
  `scripts/run_eval.py` passes `["eval"]` and uses `langsmith.evaluate` with
  `experiment_prefix="octi-eval"`. Order: 2a → 1 → 2b → 3, both after spec 02 Iteration 4.
- **Rejected:** a tracing-context tag from the caller (relies on unverified library behaviour);
  an own scoring loop with per-run feedback (changes FR-307's meaning).
- **Consequences:** spec 02 §7's entry point gains `extra_tags`; the spec tab folds it into spec 03 §7.

## S03-D-005: How a paused Analysis run is returned and resumed (Iteration 1)

- **Context:** SPEC §7 fixes the interrupt payload and resume values, not how the caller sees a pause
  or continues it; Streamlit reruns between the two halves.
- **Decision:** one module-level `InMemorySaver` (`agents/analyst/graph.CHECKPOINTER`) for every run;
  `run_analysis` returns the state with `confirmation_request` (the payload) while paused, and
  `resume_analysis(thread_id, reply, deps)` continues the same thread; a finished run's checkpoint is
  deleted. `confirmation` starts `"skipped"` when the toggle is off, so `confirm_tables` is a no-op
  node on that route (the diagram's "off" edge). `ui.analysis.is_paused` disables only the composer.
- **Rejected:** a checkpointer per call (the resumed half would not find the pause); a new return
  type (breaks spec 02's callers).
- **Consequences:** New chat during a pause leaves its checkpoint in memory (`abandon_analysis`
  exists but is not yet called from New chat, which is spec 00/01 code).
