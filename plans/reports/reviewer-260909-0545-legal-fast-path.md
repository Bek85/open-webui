# Review: legal fast path (classifier + specialist relay)

Scope: `backend/open_webui/utils/legal_fast_path.py`, `backend/open_webui/utils/legal_specialist_stream.py`, hooks in `main.py:1553-1560` and `middleware.py:2925-2935`, `deploy/native_assistant/{manage.py,legal_research.py,system.txt,test_legal_fast_path.py}`. Read-only review; claims grep-verified.

## Defects

### H1. Image attachments bypass the "no attachments" guard
- `legal_fast_path.py:77` uses `not metadata.get('files')`. Frontend builds `files` from `chatFiles` + current files but filters out `image/*` (`src/lib/components/chat/Chat.svelte:3040-3047`, `:2531-2537`); images travel only as `image_url` parts in message content.
- Scenario: user uploads a photo of a contract and asks "is this clause legal?". `metadata['files']` is empty -> candidate; `get_content_from_message` (`misc.py:170-175`) returns only the first text part -> classifier says `lexuz` -> specialist streams with the image silently discarded. Native path (model sees the image) is never reached. Contradicts the module docstring ("Document-plus-law turns keep the native tool path").
- Worse variant: when the stored image has a non-`data:` URL, `add_file_context` (`middleware.py:1621-1625`) prepends a text part `<attached_files>...` to list content, so `get_last_user_message` returns that tag block as the question and the user's real text is dropped.
- Fix: in `plan_legal_fast_path`, also bail when the last user message content is a list containing any non-`text` part (or when the stored message has `files`).

### H2. aiohttp session/response leak windows
- `legal_fast_path.py:147-158`: except tuple is `(ClientError, TimeoutError)`; `asyncio.CancelledError` (Stop button while connecting, ~600 s worst case) escapes without `session.close()`.
- `legal_specialist_stream.py:111-112`: the first two `yield`s are outside `try/finally`. Middleware consumes line 1, awaits `event_emitter` (socket + DB); a cancel during that await calls `body_iterator.aclose()` (`middleware.py:5586-5588`) -> `GeneratorExit` at a yield before the `try` -> `finalize()` never runs -> upstream response + session leak.
- `main.py:1558-1567`: if `build_chat_response_context` raises after the stream is open, the generator never starts and nothing closes it.
- Fix: wrap the whole `generate()` body in `try/finally: await finalize()` (or open the session inside the generator), and add `BaseException` cleanup around `session.post`.

### M1. Specialist in-flight statuses never closed on failure
- Relay forwards `status` frames verbatim (`legal_specialist_stream.py:120-126`) and only closes its own two steps. The tool tracks `pending_steps` and closes them with `done:true,error:true` in `finally` (`legal_research.py:212-218, 293-297`).
- Scenario: specialist emits `knowledge_search done:false`, connection drops. Message ends with "Legal research failed" but that step stays `done:false` forever in persisted `statusHistory`; FE keeps a ticking in-flight timer (`StatusHistory.svelte:65-73`).

### M2. Toggled features silently ignored
- Web search / image generation run before the hook (`middleware.py:2558, 2569`). With web search on, results are fetched, sources injected/emitted, then the model is bypassed: sources are shown for an answer that never used them; wasted search calls. Fix: exclude when `metadata['features']` has `web_search`, `image_generation` or `code_interpreter`.

### L1. `summary` frames forwarded raw
- Tool rewrites `action=='summary'` -> `reasoning` on purpose (`legal_research.py:220-222`); FE special-cases `summary` (`StatusHistory.svelte:85-88`, `StatusItem.svelte:51,160`). Relay's own final status is last, so the collapse logic is not triggered, but rendering diverges from the tool timeline.

### L2. Fallback not guaranteed on unexpected exceptions
- `start_legal_fast_path` only guards `ValueError`/aiohttp errors. E.g. malformed `LEGAL_FAST_PATH_TIMEOUT_SECONDS` -> `ValueError` at `:136` propagates to `process_chat` except -> user-facing error instead of model fallback.

### L3. Classifier determinism can be overridden
- `apply_model_params_to_body` overrides request params unconditionally (`payload.py:69-76`): base-model admin `temperature`/`max_tokens` beat the classifier's `0`/`10`. Informational; current base model presumably has none.

## Answers

1. Stream contract: OK. One `data: {...}\n\n` per yield; `[DONE]` hits the JSON-decode except and sets `done` (`middleware.py:4835-4841`); `{'event':...}` dispatched at `:4292` then falls to `choices=[]` -> `continue`; final chunk carries `finish_reason: stop` (`misc.py:698`). No hang; `content_parts` persists the answer. Caveat: event dicts pass through installed stream filters (`:4281`); a filter assuming `choices` drops that chunk silently.
2. Resources: see H2. No double-close (`finalize` runs once from `finally`; early-return paths release before returning).
3. Security: `identity_headers` is semantically identical to the tool (same `clean`, same `'|'.join(('v1',uid,email,role,chat,ts))`, same headers). No authz bypass: specialist still validates; 401/403 -> `None` -> native loop -> tool returns `access_denied` as today. Classifier output only indexes a fixed dict. No question text/identity in new log lines.
4. Fallback: every `None` return precedes any streamed byte; `metadata.pop` at `main.py:1555` clears the key on all paths. Caveat L2.
5. Ordering: relayed stream goes through `streaming_chat_response_handler`, so done event, `publish_chat_finished_event`, outlet filters, title/tags (`middleware.py:5563-5580`) all run. Regression only for web search (M2).
6. `metadata['files']` = `chatFiles` (all non-image files across the chat, restored from `chat.files` on load) + current non-image files, so earlier-turn documents are covered. Images are not (H1). Model knowledge covered by `meta.knowledge`.

## Verdict
Do not ship until H1 and H2 are fixed; M1/M2 recommended in the same change.

## Re-review (fixes in working tree)

Verified read-only against the current files; both modules parse (`ast.parse`).

- H1 fixed: `plain_text_question()` (`legal_fast_path.py:84-93`) returns `None` for any non-`text` part; `get_last_user_message` no longer used. Images (list content) now fall back to the native path.
- H2 fixed: `session.post` guarded with `except BaseException: close; raise` (`:178-180`); `generate()` wraps every yield in an outer `try/finally` awaiting the idempotent `close_upstream` (`legal_specialist_stream.py:117-152`, `legal_fast_path.py:193-200`); `main.py:1577-1583` closes upstream if `build_chat_response_context` raises. `test_finalize_runs_when_consumer_closes_early` covers aclose after first yield.
- M1 fixed: `state['pending']` keyed by `(action, started_at)`, closed with `done/ended_at/error` (`legal_specialist_stream.py:137-140, 175-179`).
- M2 fixed: `MODEL_ONLY_FEATURES` check in `is_fast_path_candidate` (`legal_fast_path.py:20, 80`).
- L1 fixed: `summary` -> `reasoning` remap (`legal_specialist_stream.py:172-174`). L2 fixed: timeout parse guarded (`legal_fast_path.py:154-157`).

### Remaining
- R1 (low, residual of H2): the middleware's response task awaits several things (queued `events`, DB upserts) before the first `body_iterator.__anext__`. A cancel or exception in that window hits `middleware.py:5586-5588`, but `aclose()` on a never-started async generator does not run its `finally`, so `close_upstream` is never called and the specialist connection leaks. Fix: in that `except asyncio.CancelledError` block (and the sibling `except Exception`), also `await` `getattr(response, 'close_upstream', None)` when present, mirroring `main.py:1580-1582`.
- R2 (low): `legal_specialist_stream.py:137-140` closes leftover specialist steps with `error: True` even on a completed stream; the tool uses `error: not completed` (`legal_research.py:294-297`). A specialist step that legitimately outlives the report would render as failed under "Legal analysis ready".

**Status:** DONE_WITH_CONCERNS
