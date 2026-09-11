# Phase 03: document intelligence

**Context:** docling OCR (`DOCLING_PARAMS`), `deploy/file_generation/`, native file context.
**Priority:** high. **Status:** in progress (2026-09-11), design revised after measuring the stack.

## Overview
Tools for what officers do with documents daily: summarize long files
(map-reduce over pages), compare two versions, extract obligations/deadlines into
a table, translate uz Latin / uz Cyrillic / ru preserving headings and tables,
with output through the existing file renderer when a file is requested.

## Revised design (2026-09-11)
Findings: the chat model serves 262 144 tokens of context; the largest uploads in
the database are ~140 000 characters (~45 000 tokens); routing (`legal_fast_path`)
is skipped whenever files are attached; a document turn delivers only top-k chunks
embedded with a local MiniLM model (weak for Uzbek) unless the file item carries
`context: 'full'`, which the UI exposes only as a manual toggle.

Therefore no separate summarize/compare/extract/translate tools: the main model
does all four when it is given the whole document. Phase 03 becomes
1. `document_context.py`: on a document turn, size-gated **whole-document context by
   default** (sum of attached files' extracted text within a cap derived from the
   model's context) with a status line, falling back to retrieval above the cap and
   telling the model so. Map-reduce for over-cap files stays out until a real need.
2. Prompt guidance for the four tasks (structure-preserving translation, comparison
   format, obligations/deadlines table columns, "you have the entire text" vs
   "excerpts only" honesty rule).
3. Routing tests: a `document-tasks` category whose e2e turns attach a fixture file.

## Requirements
- Works on 100+ page PDFs within the model's context via chunked passes with a final merge.
- Never claims whole-document coverage when only excerpts were read (existing prompt rule).
- Translation keeps structure; produced as DOCX/PDF on request.

## Related code
- Created: `backend/open_webui/utils/document_context.py` (size-gated whole-document context, system note, status), `deploy/native_assistant/test_document_context.py`, `deploy/routing_tests/cases/document-tasks.json` + `fixtures/sample-contract.txt`.
- Modified: `middleware.py` (hook before the files handler), `system.txt` (document-task guidance), routing runner (`fixture` upload) and `chat_turn.py`.
- Not created: the four separate tools from the original sketch; the model does the tasks itself once it has the whole text.

## Steps
1. Whole-document context by default within the cap (done 2026-09-11).
2. Prompt guidance for summary, comparison, obligations table, translation (done).
3. Probe with real document types; map-reduce for over-cap files only if such files appear in practice.

## Success criteria
Summary of a 100-page file under 3 minutes; table extraction verified against source on the probe set.

## Risks
Latency scales with pages (mitigate with progress statuses per chunk); quality of OCR on poor scans.
