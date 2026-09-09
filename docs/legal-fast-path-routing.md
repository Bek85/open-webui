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
UI session AND research_uzbek_law bound AND no files AND no knowledge AND legalFastPath != false
  AND no toggled web_search / image_generation / code_interpreter
  AND last user message is plain text (an image part keeps the model in charge)
  -> classify last user message (temperature 0, max 10 tokens, base model, system prompt bypassed)
     lexuz / prosecutor -> POST {RAG_BASE_URL}/<corpus>/stream with signed identity headers
                           2xx + text/event-stream -> relay as the assistant answer
                           anything else            -> native tool loop
     general           -> native tool loop (model may still call tools)
```

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
- `data: {"event": {"type": "source", ...}}` — one native source card per link
  cited in the specialist's bibliography, emitted only for completed streams.
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
| model meta `legalFastPath` | `true` | set `false` on a preset to disable |

Prosecutor access is enforced by the specialist: a 401/403 falls back to the
tool path, where the model explains the denial in the user's language.

## Tests

`deploy/native_assistant/test_legal_fast_path.py` (offline: route parsing,
eligibility, history trimming, relay/finalize/failure shapes, identity headers).
Live probes used during the investigation live only in the container under
`/tmp/na/` and are not part of the repo.
