# Legal fast path: deterministic routing in the unified chat

Module: `backend/open_webui/utils/legal_fast_path.py`. Hooks: `process_chat_payload`
(middleware, after native tools are resolved) plans the route; `chat_completion`
(main.py) starts the stream instead of calling the model when a plan exists.

## Why

Native function calling leaves the "search or answer from memory" decision to
sampling. Measured 2026-09-09 on Qwen3.8-27B (thinking off): 5/8 implicit legal
questions triggered `research_uzbek_law`; temperature 0.2 gave 1-2/8, 0.7 gave
5-6/8. Prompt and tool-description changes reached 19/24. The legacy
`router_pipeline` never had this problem because it classified first at
temperature 0 and streamed the specialist directly. This module restores that
behaviour inside the unified ProkuraturaAI chat.

## Decision per turn

```
UI session AND research_uzbek_law bound AND no knowledge AND legalFastPath != false
  AND no toggled web_search / image_generation / code_interpreter
  AND last user message is plain text (an image part keeps the model in charge)
  AND (no files, OR every file is an uploaded document the user can read whose extracted
       text fits DOCUMENT_FAST_PATH_MAX_CHARS in total)
  -> classify last user message (temperature 0, max 10 tokens, base model, system prompt bypassed);
     with files the classifier input is prefixed "[Hujjat biriktirilgan] " and the prompt says
     "about the document itself -> general, what the LAW says about it -> lexuz"
     lexuz / prosecutor -> POST {RAG_BASE_URL}/<corpus>/stream with signed identity headers
                           (+ `attachments: [{name, text}]` on document turns)
                           2xx + text/event-stream -> relay as the assistant answer
                           anything else            -> native tool loop
     any other route with files -> native tool loop (the model reads the file itself)
     wiki              -> search_encyclopedia runs server-side; its article and snippets are
                          attached as a docs file item (cited sources); the model answers
                          (utils/encyclopedia_context.py; see deploy/encyclopedia/README.md)
     file              -> the turn is narrowed to create_document / create_spreadsheet and
                          tool_choice is set to required, so the export cannot be answered in
                          prose; the model still picks format, title and arguments
                          (legal_fast_path.force_route_tools)
     calc              -> the turn is narrowed to base_calculation_value / count_deadline with
                          tool_choice required, so BHM values and deadlines come from the curated
                          tables, never from memory (deploy/legal_calculators/README.md)
     general           -> native tool loop (model may still call tools)
```

### Follow-ups

The classifier reads the previous user question together with the current one
(`classifier_text(question, has_documents, previous)`), because a continuation such as
"yaxshilab qidirib ko'r boshqacha so'zlar bilan" carries no legal signal on its own.
Measured 2026-09-11: that message alone classified `general`, the model then called the
research tool natively and the first visible text arrived after about three minutes.
The prompt rule: a continuation inherits the previous route; a new topic is judged on
its own; thanks and greetings stay `general`. Routing cases carry `previous` for this.

### Tool-call relay

When the model does call a research tool natively on a plain chat turn (one call, no
attachments), `legal_relay_plan` in `legal_fast_path.py` turns that call into a fast-path
plan and the tool loop in `middleware.py` streams the specialist instead of executing the
tool and asking the model for a second answer. The model's rewritten query becomes the
final user turn of the specialist request, after the conversation history. The
function-call item is closed with a note (`RELAY_TOOL_RESULT`); the relay stream carries
statuses, content and source cards exactly as the fast path does. Document turns and
multi-tool turns keep the loop, because the model must combine the results.

### Document turns

**Document-plus-law turns relay to the specialist in one call (since 2026-09-11).**
Before that, files disabled routing and the model's tool loop took over. Measured on a
6-page complaint with the question "what liability does Uzbek law provide for the
violations described here": the model issued three `research_uzbek_law` calls, one per
issue, the middleware ran them one after another, each was a full specialist run whose
written analysis the model then rewrote: 11 minutes end to end, about 4 of them the
specialist writing reports nobody read. Now `fast_path_documents`
(`utils/document_context.py`) collects the extracted text of every attached file, the
classifier sees the question flagged as a document turn, and on `lexuz`/`prosecutor` the
text travels in the request's `attachments` field. The specialist appends it to the
agent's history as a trailing system message (never to the user query, which is its
retrieval reference) and plans its own searches; its `ATTACHMENT_MAX_CHARS` matches the
60 000-character default here. Files over the cap, unreadable files, knowledge
collections and web items keep the model in charge, as does any non-legal route.

For the turns the model keeps (summaries, translations, questions about the document's
own wording), `utils/document_context.py` decides how much of the attachment the model sees: when the
attached files' extracted text fits `DOCUMENT_FULL_CONTEXT_MAX_CHARS` (default 450 000,
about a third of the 262K-token window) every file item gets `context: 'full'`, so the
existing files handler delivers the whole text as one source per file instead of top-k
chunks, and a status line tells the user the whole document is being read. Above the cap
retrieval stays and the model is told it only has excerpts. Either way a one-line system
note states which files were supplied in full, so the honesty rule in `system.txt` has a
fact to rely on. Measured 2026-09-11 on a 139 000-character judgment: whole document
16 s to first token, 116 s total; retrieval 22 s / 138 s.

Classifier accuracy on the mixed probe set (2026-09-09): 18/20; every legal question
stayed on the legal routes. Free model choice had called the encyclopedia on 4/8
factual questions, which is why the lookup is deterministic.

Exports are forced for the same reason. Measured 2026-09-09 on a repeat run of the
same request, free tool choice produced the file 6/7 times and, on a second wording
that had passed the suite, 5/6 — the miss moves between phrasings, so it is sampling
variance rather than a prompt defect. `tool_choice` is applied to the first request
only; the tool-call follow-up in `process_chat_response` drops it, otherwise the model
would be required to call a tool on every subsequent iteration.

The specialist receives the last 12 user/assistant turns as plain text (each
capped at 12 000 characters); it builds its own context. Attachments always take
the tool path because only the model can combine document content with law.

## Stream contract

The relay produces the SSE the middleware already understands:

- `data: {"event": {"type": "status", ...}}` — specialist status frames forwarded
  untouched (see `lexuz-status-events.md`), so the timeline renders exactly as it
  did with the legacy pipeline, summary row included. The relay adds only a
  `Researching legal sources…` placeholder until the first specialist frame, and
  `Legal research failed` on failure.
- `data: {"object": "chat.completion.chunk", ...}` — content deltas.
- `data: {"event": {"type": "source", ...}}` — native source cards emitted only
  for completed streams, in the order of the last "Manbalar" block's numbers,
  because the UI resolves an in-text `[n]` marker to the n-th card. If that
  numbering has a gap, no cards are emitted (the bibliography links stay
  clickable); without a numbered block, links are used in order of appearance.
- A stream without its completion marker keeps the partial text and appends a
  user-facing notice in the user's script; it is never presented as verified.
  Specialist steps still open at that point are closed with `error: true`, and
  the upstream connection is released exactly once, also when the viewer stops
  the response early or the request fails before the body is read.

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `RAG_BASE_URL` | `http://host.docker.internal:4040` | specialist service |
| `MCP_AUTH_SECRET` | required | signed identity (same contract as pipelines/tool) |
| `LEGAL_FAST_PATH_TIMEOUT_SECONDS` | `600` | whole-stream timeout |
| `DOCUMENT_FAST_PATH_MAX_CHARS` | `60000` | largest attached text (all files) relayed to the specialist; above it the model reads the file |
| model meta `legalFastPath` | `true` | set `false` on a preset to disable |

Prosecutor access is enforced by the specialist: a 401/403 falls back to the
tool path, where the model explains the denial in the user's language.

## Tests

Routing accuracy is gated by `deploy/routing_tests/` (classifier and end-to-end
modes with a recorded baseline); run it after any prompt, tool-description or
classifier change.

### Unit tests


`deploy/native_assistant/test_legal_fast_path.py` (offline: route parsing,
eligibility, history trimming, relay/finalize/failure shapes, identity headers).
Live probes used during the investigation live only in the container under
`/tmp/na/` and are not part of the repo.
