# Iteration 02 — From cells to a clean DataFrame

Commit SHA: (filled by student). Previous commit (Iteration 1): `08a5171`.
Spec version read before implementation and checked again before handoff: **0.7**.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-112 (grid): merged Revenue/Costs keep each year | `.venv/bin/python -m pytest -q tests/unit/test_cleaning.py` | PASS — expected five names |
| VC-114 (grid): uncovered empty cell next to Total | same command | PASS — Column N, no copied label |
| VC-115: duplicates, blanks and line breaks | same command | PASS — exact specified names; literal suffix collisions also remain unique |
| VC-117: North/South are row headers, Region kept | same command | PASS — first column only; missing labels omitted |
| VC-118: missing values → float64; whole values → int64 | same command | PASS — all FR-115 markers covered |
| VC-119: symbols, parentheses, minus, percent and footnotes | same command | PASS — exact six specified amounts; `$` and `US$` hints stay distinct |
| VC-120: columnwide European evidence; English default | same command | PASS — exact specified order plus reversed evidence; `1.234` → 1.234 |
| VC-121: text and leading-zero codes stay unchanged | same command | PASS — no partial conversion or hints |
| VC-122 (hint part): percent and currency columns | same command | PASS — builder returns `percent` and `currency: $` by column name |
| Approved overflow policy S01-D-007 | same command | PASS — both inclusive int64 bounds exact; both outside bounds preserve original text |
| Full suite green | `.venv/bin/python -m pytest -q` | PASS — 284 passed, 1 deselected in 29.68 s |
| Artifacts complete | read-only inspection | PASS — current context, two approved decisions and this record |

Final targeted result: **60 passed in 4.35 s**. Baseline: 224 passed, 1 deselected in 25.37 s.
Tests ran offline in the existing virtual environment through the host's `wsl.exe -d WLinux --cd
'<project WSL root>' -- .venv/bin/python ...` invocation. The orchestrator ran the final commands;
no installations, downloads or live checks were performed.

## TDD evidence
- Tests first, before `cleaning.py`: targeted command failed during collection with
  `ModuleNotFoundError: No module named 'agents.ingestion.pdf.cleaning'` (1 error in 11.53 s).
- Initial implementation: 56 targeted tests passed; full suite 280 passed, 1 deselected.
- Approved range tests added before the guard: targeted command returned **2 failed, 58 passed
  in 17.33 s**. Both out-of-range amounts raised `OverflowError` during int64 Series construction.
- The small signed-range guard fixed those failures; final targeted/full results above.

## Files
Added: `agents/ingestion/pdf/cleaning.py`, `tests/unit/test_cleaning.py`, this record.
Changed: `specs/01-ingestion-plan-artifacts/CONTEXT.md`, `…/DECISIONS.md` (append S01-D-006/007).
Pre-existing implementation edits carried with this iteration: accepted decision statuses in
`…/DECISIONS.md` and the acceptance note in `…/iterations/01-settings-errors-document.md`.
The Iteration 1 record was not rewritten. Deleted: none.
Spec-tab files were left untouched; no files were staged and no commit was made.

## Decisions and deviations
- S01-D-006: approved simple helper names/shapes, coordinate spans, first-seen hints and omitted
  missing row labels. No custom result classes; the module is 169 lines.
- S01-D-007: approved behavior for whole numeric columns outside int64's representable range,
  a case FR-117 does not specify. No other requirement or scope deviation.
- Conflicting decimal notation follows FR-116/117 directly: choose one style for the whole column,
  then reject incompatible separator grammar. This is not a separate conflict policy.
- No changes to spec 02's read_table, load_catalog/CatalogEntry, Index record fields or preview.

## Gotchas
- `None` in a marked header is covered only if the original cell on its left spans the full column;
  `""` is a real empty cell and never inherits a label. Merges over several columns reuse that box.
- Original text columns use pandas object dtype; later metadata maps nonnumeric dtype to `text`.
  Failed conversion preserves missing markers as written too, per FR-117.
- `Decimal` keeps whole values exact before int64 conversion; float64 is used when FR-117 requires
  it. Percent values retain their written scale. Hints exist only after successful conversion.
- WSL access is denied in the filesystem sandbox; test execution needs the approved host WSL call.

## For the next iteration
- Iteration 3 detects/joins tables and marks header rows; do not add detection to cleaning.py.
- Pass aligned header texts, horizontal cell spans (`None` for covered positions), and actual
  column extents to `flatten_headers`. Give its unique names and rectangular data rows to
  `build_dataframe`; retain the returned hints and call `row_headers` on the cleaned frame.
- Headerless tables can pass no marked rows and use the Column N fallbacks. Detection limits
  (three header rows, at least one data row, year labels) remain Iteration 3's responsibility.
- Re-read the spec Changelog before starting; v0.7's UI changes do not affect Iterations 1–2.
- Student review/staging/commit is next. Suggested message: `Add number cleaning and header flattening`.
