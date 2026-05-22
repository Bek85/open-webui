# `lexuz_pipeline.py` — Implementation Guide

This is the recipe for updating the LexUz Pipelines pipe in the **ocr-server** repo so the new research-timeline UI populates. Read alongside the event contract at [`lexuz-status-events.md`](./lexuz-status-events.md).

## Context

| Layer | Repo | Role |
|---|---|---|
| Frontend rendering | `open-webui` (this fork) | ✅ Already shipped. `StatusHistory.svelte`, `StatusItem.svelte`, `WebSearchResults.svelte` render the timeline + animations + timing. |
| open-webui backend | `open-webui` (this fork) | ❌ No change. |
| Pipelines runtime | `github.com/open-webui/pipelines` (upstream image) | ❌ No change — consume `ghcr.io/open-webui/pipelines:main` as-is. |
| **LexUz pipe** | **`gitlab.bp.gov:bek85/ocr-server`** | ⚠️ **This file**: `openwebui/pipelines/lexuz_pipeline.py` — replace it. |
| RAG / SSE emitter | `crawler-lexuz` (separate repo) | ⚠️ Must emit named SSE events per the contract. Not in scope of this guide. |

Deployment context (gaudi host):

- `pipelines` container = `ghcr.io/open-webui/pipelines:main`, port `9099`
- Bind mount: host `/home/user/ocr-server/openwebui/pipelines/` → container `/app/pipelines`
- The Pipelines server **hot-reloads** `.py` files on save — no container restart needed for iteration. Compose `restart` only required if env vars change.

## How a pipe emits status events

The open-webui Pipelines runtime recognises a special dict shape yielded from `pipe()`:

```python
yield {
    "event": {
        "type": "status",
        "data": {
            "action": "knowledge_search",
            "query": "...",
            "items": [...],
            "done": False,
            "started_at": 1716383821123,
        }
    }
}
```

That dict is forwarded over the OpenAI-compatible chat completion stream as a marker frame; open-webui's chat handler picks it up and routes it to the user's socket.io `events` channel as `type:"status"`. The frontend then appends it to `message.statusHistory`. Source: [`open-webui/pipelines/examples/pipelines/events_pipeline.py`](https://github.com/open-webui/pipelines/blob/main/examples/pipelines/events_pipeline.py).

Regular content frames are yielded as plain strings:

```python
yield "Бизнинг жавоб..."
```

The pipe may interleave the two freely.

## What needs to change in `lexuz_pipeline.py`

Today the pipe is a dumb byte-forwarder — it streams whatever crawler-lexuz returns straight into the assistant message body. Everything emoji-prefixed (e.g. `> 🔍 So'rov tahlil qilinmoqda...`) lands as plain markdown text inside the answer, with no socket.io events emitted. That's why the UI shows nothing useful in the timeline.

The new pipe must:

1. **Open the upstream SSE stream from crawler-lexuz.** The upstream URL stays the same: `LEX_UZ_RAG_URL` (today `http://172.18.35.124:4040/lex_uz/stream`).
2. **Parse named SSE frames.** Each frame is one of:
   - `event: message` + `data: <text>` → forward `data` as content (`yield text`)
   - `event: status` + `data: <json>` → forward as event (`yield {"event": {"type": "status", "data": <parsed json>}}`)
   - Bare `data: <text>` with no `event:` line → treat as `message` (backward-compat with the current stream).
3. **Emit synthetic start/end markers.** When the pipe begins, drop a `{"description":"", "done":False}` status to clear any stale state; when the pipe finishes, drop a `{"done":True}` to close the timeline.
4. **Keep timeouts, error handling, and `Valves` configuration identical** to today's pipe — don't regress on production resilience.

## Drop-in replacement

This is the complete file. Replace `openwebui/pipelines/lexuz_pipeline.py` in the ocr-server repo with this content.

```python
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)


class Pipeline:
    """LexUz RAG pipe with structured research-timeline events.

    Translates named SSE frames from crawler-lexuz (`event: message`,
    `event: status`) into open-webui Pipelines events. See
    docs/lexuz-status-events.md in the open-webui repo for the
    event contract.
    """

    class Valves(BaseModel):
        LEX_UZ_RAG_URL: str = ""
        REQUEST_TIMEOUT: int = 600

    def __init__(self):
        self.name = "LexUz"
        self.valves = self.Valves(
            **{
                "LEX_UZ_RAG_URL": os.getenv(
                    "LEX_UZ_RAG_URL",
                    "http://host.docker.internal:4040/lex_uz/stream",
                ).strip(),
                "REQUEST_TIMEOUT": int(os.getenv("REQUEST_TIMEOUT", "600")),
            }
        )
        self.session = requests.Session()

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        self.session.close()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        LEX_UZ_RAG_URL = self.valves.LEX_UZ_RAG_URL
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

        payload = body.copy()
        for field in ("user", "chat_id", "title"):
            payload.pop(field, None)

        try:
            r = self.session.post(
                url=LEX_UZ_RAG_URL,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            r.raise_for_status()

            def gen():
                # Open the timeline so any stale rendering is cleared.
                yield {
                    "event": {
                        "type": "status",
                        "data": {"description": "", "done": False},
                    }
                }
                try:
                    yield from _parse_and_forward(r)
                except requests.exceptions.ChunkedEncodingError:
                    logger.error("Upstream response ended prematurely")
                    yield "Error: Upstream response ended prematurely"
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed during streaming: {e}")
                    yield f"Error: Request failed during streaming - {e}"
                except Exception as e:
                    logger.exception(f"Unexpected error during streaming: {e}")
                    yield f"Error: Unexpected error during streaming - {e}"
                finally:
                    # Close the timeline.
                    yield {
                        "event": {
                            "type": "status",
                            "data": {"description": "", "done": True},
                        }
                    }
                    r.close()

            return gen()

        except requests.exceptions.Timeout:
            return f"Error: Request timed out after {self.valves.REQUEST_TIMEOUT}s"
        except requests.exceptions.RequestException as e:
            return f"Error: Request failed - {e}"
        except Exception as e:
            return f"Error: Unexpected error - {e}"


def _parse_and_forward(response):
    """Iterate an SSE response and yield content strings or event dicts.

    SSE frames are delimited by blank lines. Each frame may contain:
      event: <name>
      data: <line 1>
      data: <line 2>

    For multi-line `data` fields the concatenated lines are joined with \\n,
    per the SSE spec. We forward `event: message` (and bare frames) as content,
    and `event: status` as parsed-JSON events.
    """
    event_name = None
    data_lines: List[str] = []

    for raw_line in response.iter_lines(decode_unicode=True):
        # iter_lines yields None on keepalive bytes; treat any falsy line as a
        # frame delimiter only if we actually accumulated something.
        if raw_line is None:
            continue
        line = raw_line.rstrip("\r")

        if line == "":
            # End of a frame. Emit and reset.
            if data_lines or event_name:
                yield from _emit_frame(event_name, "\n".join(data_lines))
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            # SSE comment — ignored.
            continue

        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            # Trim a single optional leading space after the colon.
            chunk = line[len("data:"):]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            data_lines.append(chunk)
        # All other field names (id:, retry:, etc.) are not used.

    # Flush a trailing frame if the stream ends without a blank line.
    if data_lines or event_name:
        yield from _emit_frame(event_name, "\n".join(data_lines))


def _emit_frame(event_name, data_str):
    """Yield the right shape based on event name."""
    if event_name == "status":
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("status frame had invalid JSON; dropping: %r", data_str[:200])
            return
        yield {"event": {"type": "status", "data": payload}}
        return

    # Default branch: treat as content. Covers `event: message`, no event name,
    # and any unknown event we want to be forgiving about.
    if data_str:
        yield data_str
```

## Diff summary (vs. current `lexuz_pipeline.py`)

- `requests` → adds `Accept: text/event-stream` to the headers (so crawler-lexuz knows to send SSE format).
- The `stream_response` inner generator is replaced with a real SSE parser (`_parse_and_forward`) and an event hoister (`_emit_frame`).
- Two synthetic events (open + close) bracket the stream so the UI's "currently working" state is clean across edge cases.
- Logging unchanged; error returns unchanged.

## How to apply the change

Path A — recommended (clean, reviewable):

1. `git clone git@gitlab.bp.gov:bek85/ocr-server.git`
2. Edit `openwebui/pipelines/lexuz_pipeline.py` with the drop-in above.
3. `git commit -m "feat(pipelines): translate crawler-lexuz SSE events into open-webui timeline"`
4. Push, open MR, merge.
5. On gaudi: `cd /home/user/ocr-server && git pull`. Pipelines hot-reloads the `.py` automatically — no `docker compose restart pipelines` needed.

Path B — hot patch on gaudi (for live iteration before committing):

1. SSH gaudi, `vi /home/user/ocr-server/openwebui/pipelines/lexuz_pipeline.py`, paste, save.
2. Watch logs: `docker logs -f pipelines | grep -i lexuz`.
3. Once it works end-to-end, commit the same diff to the ocr-server repo via Path A so the file isn't lost on next deploy.

## Verifying end-to-end

Prerequisites: crawler-lexuz must already emit named SSE events per [`lexuz-status-events.md`](./lexuz-status-events.md). Until it does, this pipe will just forward all bytes as content — same behaviour as today (safe fallback).

Once both ends are aligned:

1. Open the open-webui chat at `https://ai.prokuratura.uz/` (or your local dev build of this repo at `http://localhost:5173`).
2. Send the example Cyrillic legal query.
3. Expected sequence:
   - Timeline opens with the first `knowledge_search` row, shimmering label, breathing dot, live ticking duration.
   - Each retrieved Qdrant hit appears with a staggered fly-in animation, showing `DD.MM.YYYY. Title ... lex.uz` on the right.
   - The summary row appears as the final timeline event with the model-generated title.
   - Once the assistant token stream starts, the timeline auto-collapses to a single line: `"Legal analysis of Uzbek criminal code provisions · 4.2s ✓"`.
   - Clicking the header re-expands all rows.

If the timeline stays empty:

- `docker logs pipelines | tail -50` — check for parsing errors.
- Inspect raw SSE: `curl -N -H 'Accept: text/event-stream' http://172.18.35.124:4040/lex_uz/stream -d '{"messages":[{"role":"user","content":"тест"}]}'` — confirm the upstream is actually emitting `event: status` frames.
- Browser DevTools → Network → WebSocket → look for `events` messages with `type:"status"`.

## Open questions

- Crawler-lexuz must emit `started_at` / `ended_at` for the timing display to work. If those fields are missing on `status` events the per-step duration will not render (only the total falls back to a wall-clock derivation in the UI).
- `lexuz_pipeline.py` does not currently consume the `summary` event differently from other statuses — it's just forwarded. The frontend handles the collapsed-header treatment. No pipeline-side change needed for that.
