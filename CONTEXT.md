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

**Table context**:
The text around a Table in its PDF that tells what the Table is about: section title, caption,
the text just before and after it, and its footnotes.
_Avoid_: surroundings, nearby text

**Table preview**:
The first few rows of a Table, kept with its Table metadata so a reader can recognize the Table
without loading its data.
_Avoid_: sample, snippet

**Document**:
One PDF in the catalog, identified by its file name. Uploading a file with the same name replaces
the Document and all its Tables.
_Avoid_: file, upload, report

**Skipped part**:
A page, table or image of a Document that Octi could not read or could not describe correctly. It
is reported to the user and never indexed.
_Avoid_: error, failed table, missing page

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
