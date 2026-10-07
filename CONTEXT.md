# Octi

Question answering over tables found in machine-readable PDFs: one agent ingests PDFs into a
searchable catalog of tables, another answers questions by computing over the selected tables.

## Language

### Tables

**Table**:
One logical table from a PDF. A table that continues onto the next page is still one Table.
_Avoid_: page table, fragment, chunk

**Table metadata**:
The descriptive fields of a Table: name, description, columns, row headers and source.
_Avoid_: annotations, enrichment

**Table store**:
Where the data (cells) of every Table lives, keyed by its `table_id`.
_Avoid_: database, cache

**Index record**:
The vector-database entry for one Table: its embedding plus its Table metadata.
_Avoid_: vector, document, chunk

### Runs

**Ingestion run**:
One execution of the ingestion agent over one PDF.
_Avoid_: upload, import job

**Analysis run**:
One execution of the analyst agent over one question.
_Avoid_: query, chat turn

### Answering

**Candidate table**:
A Table returned by retrieval as possibly relevant to a question.
_Avoid_: hit, match, result

**Selected table**:
A Candidate table chosen to be used in the calculation.
_Avoid_: chosen table, input table

**Answer status**:
The outcome of an Analysis run: `answered`, `partial` or `cannot_answer`.
_Avoid_: result type, success flag
