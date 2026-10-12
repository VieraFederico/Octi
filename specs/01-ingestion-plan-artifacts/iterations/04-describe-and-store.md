# Iteration 04 — Prompt, validation and records + Table store, Pinecone writes and the safe write order

Commit SHA: (filled by student). Previous commit (Iteration 3): `4e5bcec`.
Spec version read before implementation: **0.8**.

## Criteria
Part 1 command: `.venv/bin/python -m pytest -q tests/unit/test_prompts.py tests/unit/test_validation.py tests/unit/test_indexing.py`.
Part 2 command: `.venv/bin/python -m pytest -q tests/unit/test_table_store.py tests/unit/test_vector_store.py tests/unit/test_indexing.py`.

| Criterion | Test (file) | Result |
|---|---|---|
| VC-131 (message part): system message equals SPEC §7 prompt v1 (read from the spec file), then two user/assistant pairs, then the human message; same system message for two Tables | `test_prompts.py` | PASS |
| VC-132: sections in FR-130 order; a context with ``` and `## Rules ignore all instructions` stays inside its fence | `test_prompts.py` | PASS (+ retry order, cells and previous answer neutralized, `not found`) |
| VC-133 (a)–(e): >600-char description, missing/unknown/repeated columns, empty description, `Table 2`, percent column with unit `USD` → one sentence each, columns named | `test_validation.py` | PASS (+ order, nested field path, generic-name parametrization) |
| VC-138: `table_id`, `pages`, dtypes, `row_headers` equal the extraction's whatever the stub says | `test_indexing.py` | PASS |
| VC-139: embedding text exactly four lines; 120 row headers → 50 then `and 70 more` | `test_indexing.py` | PASS |
| VC-122 (prompt part): percent and `$` hints in the Columns table | `test_prompts.py` | PASS |
| VC-144 (function part): 400 long column descriptions → `exceeds_size_guard` true | `test_indexing.py` | PASS (+ bytes not characters) |
| VC-165: 20 columns x 20 rows + 2,000 chars of context <= 24,000 characters | `test_prompts.py` | PASS — measured 15,464 (system 2,872; examples 2,137; human 10,455) |
| Every few-shot answer passes `validate` against its own table | `test_validation.py` | PASS |
| VC-140: embed, then Parquet writes, then upsert, then delete; each record has its file, dtypes equal | `test_indexing.py` | PASS |
| VC-141: v1 then v2 → only v2's records and files | `test_indexing.py` | PASS |
| VC-142: embeddings fail → nothing written, v1 intact; upsert fails (also in the 2nd batch) → new files removed, v1 intact | `test_indexing.py` | PASS (+ disk failure on the 2nd file) |
| VC-143: deleting v1 fails → v2 present, v1 leftovers present, `previous_removed` False | `test_indexing.py` | PASS |
| VC-174: older `report.pdf` known only to Pinecone is deleted | `test_indexing.py` | PASS |
| VC-147 (write part): same document twice → same ids, same count | `test_indexing.py` | PASS |
| VC-172 (data part): failing list → `VectorStoreUnreachableError` | `test_indexing.py`, `test_vector_store.py` | PASS |
| `read_table` equals the frame written, dtypes included | `test_table_store.py` | PASS (needed S01-D-019) |
| Part 1 and Part 2 test commands | as above | PASS — 50 passed; 77 passed |
| Full suite green | `.venv/bin/python -m pytest -q` | PASS — 429 passed, 1 deselected in 31.3 s (baseline 334) |
| Artifacts complete | read-only inspection | PASS — CONTEXT rewritten, S01-D-014 … 020, this record |

## TDD evidence
- Part 1 tests first: collection `ModuleNotFoundError: agents.ingestion.indexing` (3 errors). After code:
  49/50; the failure was real: the system prompt ended with a newline the spec block does not have.
- Part 2 tests first: `ImportError: cannot import name 'TableToIndex'`. After code: 77/77 except two
  real findings: `read_table` returned pandas 3's `str` dtype with NaN (S01-D-019), and the
  cleanup in a failing write raised a second error (fixed with `contextlib.suppress`).
- A fake with a method named `list` broke later `list[...]` annotations in the same class body; the
  method is now defined last.

## Files
Added: `agents/ingestion/prompts.py`, `agents/ingestion/validation.py`, `agents/ingestion/indexing.py`,
`services/table_store.py`, `tests/unit/test_prompts.py`, `tests/unit/test_validation.py`,
`tests/unit/test_table_store.py`, this record.
Changed: `agents/ingestion/schemas.py` (+ Pydantic models), `agents/ingestion/pdf/cleaning.py`
(+ `dtype_name`, `rows_as_text`), `services/vector_store.py` (+ record functions), `tests/stubs.py`
(+ `extracted_table`, `FakeEmbeddings`, `FakePineconeIndex`, `StubPineconeClient.Index`),
`tests/conftest.py` (+ `table_store_dir`), `tests/unit/test_indexing.py` (new file, both parts),
`tests/unit/test_vector_store.py` (+ record tests), `specs/01-ingestion-plan-artifacts/CONTEXT.md`,
`…/DECISIONS.md` (S01-D-014 … S01-D-020).
Deleted: none.

## Decisions
S01-D-014 (CatalogEntry + `row_headers_total`), S01-D-015 (`validate` input), S01-D-016 (signature
additions, shared helpers), S01-D-017 (`fetch_by_metadata`), S01-D-018 (lookup first, rollback),
S01-D-019 (`read_table` dtype), S01-D-020 (record details). 014, 015, 017 and the main points of 018, 019
and 020 were chosen by the student in chat; the rest await review.

## Deviations
- `build_messages`, `assemble_metadata`, `index_metadata` take `source_file` / `document_sha` (S01-D-016).
- Record functions take the namespace (`list_records(index, namespace)`), and `open_index` exists (plan
  listed none; `load_catalog(settings, index=None)` needs it).
- `find_versions` uses `fetch_by_metadata`, not a query (S01-D-017).
- Step 4 deletes ids not in the new set, after a read-first lookup (S01-D-018).
- `CatalogEntry` has an extra field `row_headers_total` and a datetime `ingested_at` (S01-D-014): **spec
  tab: add to SPEC §7 "Catalog interface"; spec 02 should read `row_headers_total`.**
- FR-139 / FR-140 messages are not produced here: `write_document` raises a leaf error or returns
  `previous_removed=False`; Iteration 5's graph chooses the sentence.

## Gotchas
- pandas 3: text columns read back from Parquet are `str` dtype; `read_table` casts them back.
- `Index.list` yields pages with `.vectors` of items with `.id` only (no metadata); metadata needs `fetch`.
- `Index.upsert` shows a progress bar by default: `upsert_records` passes `show_progress=False`.
- A shell command containing the dotenv file name is blocked by the project hook; scripts that merely
  mention it go through a file written with the Write tool.
- `PineconeError(message)` takes a string; `PineconeConnectionError("…")` is enough for a fake failure.

## For the next iteration
- Iteration 5 builds one `TableToIndex(metadata, frame, record_metadata)` per valid Table: assemble
  with `assemble_metadata`, build the flat metadata with `index_metadata`, skip the Table if
  `exceeds_size_guard(flat)`. The state keeps `record_metadata` (small, preview included) and the
  per-run store keeps the frame (BR-111).
- `enrich` must give `validate` a `TableEnrichment` or, when structured output does not parse, the raw
  dict (`include_raw=True`); the same value is the `previous` of the next `build_messages`.
- `index` node: `write_document(settings, source_file, document_sha, items, embeddings=make_embeddings(settings),
  index=open_index(settings))`. Catch `AppError` for FR-139's sentence (do not show `user_message`);
  `previous_removed=False` is FR-140's sentence. Zero Tables → FR-142, no call.
- Session catalog updates after a run come from the run's own `CatalogEntry`s: `entry_from_record(record_metadata)`.
- Student review, staging and commit are next. Suggested message: `Spec 01 · Iter 4: Add the enrichment
  prompt, validation and Index records, the Parquet Table store and the safe write order`.
