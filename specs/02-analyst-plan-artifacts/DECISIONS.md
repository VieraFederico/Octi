# DECISIONS — Spec 02 Analyst agent (spec-local, `S02-D-NNN`)

Project-wide decisions are in the root `DECISIONS.md` (D-085 … D-116 for this spec).

## S02-D-001: Counts and conditional rules are enforced by code, not Pydantic validators (Iteration 1)
- **Context:** SPEC §7 comments say `parts` has at least 1 entry, `search_phrases` 1–3, and
  `missing` is required unless the verdict is `answerable`.
- **Decision:** the models carry these rules only in their `Field` descriptions (the LLM reads
  them). `check_selection` enforces `missing` (with a retry, FR-212); Iteration 3 keeps the first 3
  search phrases and handles a plan with no part.
- **Rejected:** `min_length` / `max_length` / model validators — a fourth search phrase would make
  the whole structured-output call fail to parse instead of being trimmed or getting feedback.
- **Consequences:** the models accept out-of-range counts; code downstream must not assume them.

## S02-D-002: Plain data shapes shared by prompts, checks and graph live in `schemas.py` (Iteration 1)
- **Context:** the plan names functions taking a window, a previous attempt, facts, and returning a
  failure kind; their shapes were not fixed.
- **Decision:** frozen dataclasses `Turn(question, answer)`, `PreviousAttempt(code, feedback)`,
  `AttemptCheck(failure, feedback, emitted)`, `TableSource(name, source_file, pages)`,
  `AnswerFacts(question, parts, outcomes, approach, tables, answer_status)`, next to the §7 models
  (as spec 01 keeps `ExtractedTable` in its `schemas.py`). Failure kinds: `python_error`, `timeout`,
  `invalid_output`, `wrong_parts`.
- **Rejected:** plain dicts (no types to check); Pydantic models (no LLM reads them).
- **Consequences:** `attempts_history` (Iteration 3) records these failure-kind names; the UI and
  spec 03 read them.

## S02-D-003: Signature mappings from the plan to the contract (Iteration 1)
- **Context:** the plan's signatures miss data a retry needs; spec 01 names win (`CatalogEntry`).
- **Decision:** `build_select_messages(plan, candidates, previous=None, feedback=())` and
  `build_respond_messages(facts, previous=None, feedback=())` carry the retry inputs (FR-212,
  FR-229); `build_code_messages(plan, selection, selected, aliases, previous=None)` takes the
  selection to keep only `answerable` parts and show each part's tables; `classify_attempt(...,
  timeout_seconds)` names N in the timeout feedback; `candidate_block(entry)` is public for VC-246;
  candidates and Selected tables are `CatalogEntry`; one sentence `ONLY_GIVEN_DATA` serves VC-241.
  At integration: `check_numbers` returns one `NUMBER_FEEDBACK` sentence per offending number (the
  `respond` retry's feedback, like `check_selection`), not the bare numbers.
- **Rejected:** keeping the plan's exact signatures and building retries elsewhere.
- **Consequences:** Iteration 3's nodes call these signatures.

## S02-D-004: Feedback sentences the spec leaves open (Iteration 1)
- **Context:** FR-212 and FR-221 fix the meaning of the feedback, not every sentence.
- **Decision:** the constants in `checks.py` (`UNKNOWN_TABLE_FEEDBACK`, `MISSING_PART_FEEDBACK`,
  `DUPLICATE_PART_FEEDBACK`, `EXTRA_PART_FEEDBACK`, `EMPTY_MISSING_FEEDBACK`, `NOT_JSON_DETAIL`,
  `WRONG_PARTS_*`). Extras: a non-zero exit with blank stderr (killed for memory) gets
  `SILENT_EXIT_FEEDBACK`; a part emitted `missing` with a blank reason gets `EMPTY_MISSING_REASON`;
  an `answerable` part with no `table_ids` is a selection problem (`NO_TABLE_FEEDBACK`; student
  choice, not in FR-212 yet — flagged to the spec tab).
- **Rejected:** letting each package word its own sentences.
- **Consequences:** feedback is for the model and traces only, never the chat (BR-206).

## S02-D-005: How the number check reads numbers (Iteration 1)
- **Context:** FR-229 allows thousands separators, rounding to the shown precision and scale words;
  answers may be in Spanish (D-103), and percent ↔ fraction is an allowed conversion (rule 3).
- **Decision:** each token is read English-style and Spanish-style where well-formed; it passes when
  a reading matches a computed value's absolute value within half a unit of its shown decimals, ×
  1000^k with a scale word, × 100 with `%`; or equals any number written in the facts, a page or a
  part number.
- **Rejected:** only the years and pages of the facts (rejects "top 3" copied from the question);
  English-only parsing (rejects every Spanish answer).
- **Consequences:** lenient on reformatting, strict on invented figures; a sign is not checked.

## S02-D-006: Alias rule for Selected tables (Iteration 1)
- **Context:** SPEC §7: "short, unique snake_case names derived from the Table names".
- **Decision:** ASCII-fold, lowercase, non-alphanumerics → `_`, cut to 30 characters at a word
  boundary, then `table` when empty, `t_` before a leading digit, `_2`, `_3` for repeats (the prefix
  and suffix may add a few characters after the cut). A cut that ends exactly at a word end keeps that
  word; the code few-shot's alias equals what `make_aliases` derives (seam test).
- **Rejected:** `t1`, `t2` (meaningless in code); full names (long, unstable keys).
- **Consequences:** the alias is a valid Python identifier; the code prompt and the prelude share it.

## S02-D-007: `emit` details (Iteration 1)
- **Context:** FR-226 names NaN, None, infinite and "neither a number nor text".
- **Decision:** numpy scalars become Python values; bool, `pd.NA` / `NaT` and any other type count as
  "neither"; one bad value turns the whole part `missing` with FR-226's reason; non-`answered` parts
  drop their values; non-dict parts pass through (the app's validation reports them); modules bound
  as default arguments; ASCII JSON with `allow_nan=False`, flushed.
- **Rejected:** dropping only the bad value (a partial result looks complete).
- **Consequences:** a yes/no answer must be emitted as text, not a bool.

## S02-D-008: Message layout and the `select` cap order (Iteration 1)
- **Context:** FR-209 caps a candidate block at 3,500 characters but a table with long column names
  can exceed it even with 40 columns.
- **Decision:** one human message per call with `#` sections (as spec 01 FR-130); the window is
  fenced inside it, not replayed as chat turns. Over-long blocks drop columns from the end, then row
  headers, then preview lines. No few-shot for `understand` and `respond`. Few-shots use invented
  tables, not the sample PDFs.
- **Rejected:** a hard character cut (can break a fence); replaying turns as messages (window text
  would read as instructions).
- **Consequences:** few-shots never teach the evaluation's own questions (spec 03).

## S02-D-009: Template answer format (Iteration 1)
- **Context:** FR-229 needs a code-built answer from the same facts.
- **Decision:** `Question N: label = value.` per answered part, `Method: …`, `Sources: name (file,
  page N).`, `Question N could not be answered: reason.`; English; numbers with `,` thousands and at
  most 4 decimals, so they pass `check_numbers`.
- **Rejected:** translating the template (needs an LLM).
- **Consequences:** a fallback answer to a Spanish question is in English.

## S02-D-010: No method in the `respond` facts for `cannot_answer` (Iteration 1)
- **Context:** FR-227 lists `approach` among the facts; with no part computed, the approach can
  describe a calculation that produced nothing.
- **Decision:** for `cannot_answer`, `build_respond_messages` shows `# Method` as `none` (the prompt
  then leaves the method sentence out); the reasons and the sources stay. Student choice.
- **Rejected:** keeping the approach (misleading next to "no result").
- **Consequences:** FR-227's wording could note it (flagged to the spec tab).

## S02-D-011: `select` size checks and the last-resort cut (Iteration 1)
- **Context:** WP-A pinned the fixed part (system + few-shots + question) at ≤ 4,500 characters, so
  any word change broke a test; a block can exceed 3,500 after every shortening step only through a
  huge name or description.
- **Decision:** VC-246 (each block ≤ 3,500, whole prompt ≤ 40,000 for 10 maximum-size candidates) is
  the binding size test; the fixed-part test is removed. Last resort: hard cut to 3,499 characters
  plus `…` (no fence remains at that point). The question and its parts are not capped. Student choice.
- **Rejected:** capping the question text (a new rule for a case not seen).
- **Consequences:** 39,552 of 40,000 characters measured; a very long question can exceed the total.
