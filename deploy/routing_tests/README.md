# Routing test suite

Free model tool choice on this deployment is a sampling coin flip (measured
2026-09-09: 5/8 legal, 4/8 encyclopedia). Routing therefore has a deterministic
first hop (temperature-0 classifier in `backend/open_webui/utils/legal_fast_path.py`)
and this suite keeps it measurable. Run it after every change to the system
prompt, a tool description, the classifier prompt, or the model server.

## Layout

| Path | Purpose |
|---|---|
| `cases/<category>.json` | representative requests per tool: `route` the classifier must return, `tool` the turn must use; each case has `text` and `script` (uz-latn, uz-cyrl, ru); optional `history` for turns that refer to a previous answer |
| `run_routing_tests.py` | runner; `--mode classifier` (fast) or `--mode e2e` (real chat turns); `--category`, `--limit`, `--update-baseline` |
| `chat_turn.py` | one real chat turn summarised: tool calls, legal fast path, encyclopedia sources, timings |
| `baseline.json` | recorded hit rate per category and mode; the runner exits 1 below it |

Categories: `legal-research`, `prosecutor-orders`, `encyclopedia`, `file-creation`, `no-tool`.
Classifier classes: `lexuz`, `prosecutor`, `wiki`, `file`, `general`.

## Running

```sh
docker cp deploy/. open-webui:/tmp/deploy/
docker exec -e PYTHONPATH=/app/backend:/tmp/deploy/native_assistant -w /tmp/deploy/routing_tests open-webui \
  python run_routing_tests.py --mode classifier            # ~1 s per case, run this on every prompt change
docker exec -e PYTHONPATH=/app/backend:/tmp/deploy/native_assistant -w /tmp/deploy/routing_tests open-webui \
  python run_routing_tests.py --mode e2e --limit 3         # ~30-90 s per case; temporary chats, never persisted
```

Baselines are only rewritten by a full run (`--update-baseline` without
`--limit`/`--category`). Raise a baseline after a genuine improvement; never
lower one to make a run pass.

## What "used" means in e2e mode

Legal categories count the specialist fast path (status `Researching legal sources…`)
or a research tool call; `encyclopedia` counts encyclopedia sources (the
server-side lookup delivers them as `sources` in the completion payload) or a
tool call; `file-creation` counts either file tool; `no-tool` requires none of
these. `file-creation` is forced rather than sampled: the `file` class narrows the
turn to the file tools and sets `tool_choice=required`, so a miss there now means
the classifier misrouted, not that the model declined.

## Adding a tool category

1. Add `cases/<category>.json` with 8-18 requests across the three scripts.
2. If the tool gets its own classifier class, add it to `CLASSIFY_SYSTEM` and `parse_route`.
3. Run both modes, record the baseline in the same commit as the tool.
