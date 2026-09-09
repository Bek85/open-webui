# Phase 03: document intelligence

**Context:** docling OCR (`DOCLING_PARAMS`), `deploy/file_generation/`, native file context.
**Priority:** high. **Status:** planned.

## Overview
Tools for what officers do with documents daily: summarize long files
(map-reduce over pages), compare two versions, extract obligations/deadlines into
a table, translate uz Latin / uz Cyrillic / ru preserving headings and tables,
with output through the existing file renderer when a file is requested.

## Requirements
- Works on 100+ page PDFs within the model's context via chunked passes with a final merge.
- Never claims whole-document coverage when only excerpts were read (existing prompt rule).
- Translation keeps structure; produced as DOCX/PDF on request.

## Related code
- Create: `deploy/document_tools/workspace_tool.py` (summarize, compare, extract_table, translate_document), instructions, tests.
- Modify: `manage.py` COMPANION_TOOLS, prompt, UI captions.

## Steps
1. Chunking helper over extracted file text (reuse WebUI file extraction).
2. Summarize + extract_table first (highest use), then compare, then translate.
3. Probe with 5 real document types (anonymized).

## Success criteria
Summary of a 100-page file under 3 minutes; table extraction verified against source on the probe set.

## Risks
Latency scales with pages (mitigate with progress statuses per chunk); quality of OCR on poor scans.
