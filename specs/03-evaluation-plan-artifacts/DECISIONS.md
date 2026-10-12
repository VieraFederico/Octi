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
