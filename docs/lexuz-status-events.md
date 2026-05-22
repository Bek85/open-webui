# LexUz Research-Timeline Event Contract

The `crawler-lexuz` pipeline emits status events that drive the research timeline UI in this open-webui fork. This document is the source of truth for what the pipeline must send.

All events use open-webui's existing `event_emitter` transport. No transport changes are required on this side.

```python
# inside the pipeline
await __event_emitter__({"type": "status", "data": {...}})
```

The event router on open-webui's side appends every `type:"status"` event to `message.statusHistory`. The UI (`src/lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte`) renders that array as a vertical timeline, with the **last** entry shown as the collapsed-state header.

---

## Required envelope

Every event:

```jsonc
{
  "type": "status",
  "data": {
    "action": "reasoning" | "knowledge_search" | "summary" | /* ... existing actions ... */,
    "description": "<human-readable label, English source for i18n>",
    "done": true | false,
    "started_at": 1716383821123,   // unix milliseconds (REQUIRED on first emit)
    "ended_at":   1716383822456,   // unix milliseconds (REQUIRED on final emit when done:true)
    "duration_ms": 1333             // optional pre-computed convenience
    // action-specific fields below
  }
}
```

Rules:

- `started_at` is REQUIRED on the first emit of a step (typically `done:false`).
- `ended_at` is REQUIRED on the final emit of a step (`done:true`). Omit until the step is genuinely finished.
- Steps may re-emit multiple times. `started_at` stays constant across re-emits; only the final emit carries `ended_at`.
- If a step finishes in <50 ms the UI hides its duration display; the timestamps should still be set.

---

## Action: `reasoning`

A paragraph of agent narration shown as a timeline item. Markdown is supported.

```jsonc
{
  "type": "status",
  "data": {
    "action": "reasoning",
    "description": "I need to find the current text of Article 103-1 to verify the aggravating circumstances listed in the statute.",
    "done": true,
    "started_at": 1716383820000,
    "ended_at":   1716383820280
  }
}
```

- Emit one event per paragraph so each appears as a discrete item.
- Inline markdown is rendered. Avoid block-level constructs (lists, headings) — they look out of place inside a timeline row.
- Optional. Omit if the pipeline does not generate intermediate reasoning.

---

## Action: `knowledge_search`

A Qdrant query and its hit list. Renders as a collapsible card with query header + result rows.

```jsonc
{
  "type": "status",
  "data": {
    "action": "knowledge_search",
    "query": "Ўзбекистон Жиноят кодекси 103-модда ўзини ўзи ўлдиришга ундаш",
    "count": 6,
    "items": [
      {
        "title":   "Ўзбекистон Республикасининг Жиноят кодекси",
        "link":    "https://lex.uz/docs/111453",
        "date":    "22.09.1994",
        "snippet": "...optional chunk text, reserved for v2 (not displayed in v1)...",
        "score":   0.84
      }
    ],
    "done": true,
    "started_at": 1716383820300,
    "ended_at":   1716383821640
  }
}
```

- `items[].link` is REQUIRED. Used for favicon (Google s2 service), domain on the right, and click-through.
- `items[].title` falls back to `link` when missing.
- `items[].date` is prefixed to the title in the UI in gray (`DD.MM.YYYY. Title`).
- `items[].snippet` is reserved — store it now, the v2 UI will show it on row click without any pipeline change.
- `count` should equal `items.length` (or be the total when paginated). Used in the "Retrieved N results" header.
- For a single bare URL fetch, use `urls: ["https://lex.uz/docs/3515278"]` instead of `items`.

---

## Action: `summary` (REQUIRED — last event of the turn)

Single event emitted **after all tool calls and before the assistant token stream begins**. Drives the collapsed-state header and the total elapsed time.

```jsonc
{
  "type": "status",
  "data": {
    "action": "summary",
    "description": "Organized comprehensive legal analysis of Uzbek criminal code provisions",
    "done": true,
    "started_at": 1716383820000,   // = started_at of the FIRST event in the turn
    "ended_at":   1716383824200,   // = when the agent finished all tool calls
    "duration_ms": 4200             // total agent time
  }
}
```

- `description` is the one-line title shown in the collapsed view. Pipeline-generated via one extra small-model LLM call ("summarize what I just did, ≤10 words").
- If this event is omitted, the UI falls back to a static `"Legal research"` label, computes total time from first/last timestamps, and still works — but the header reads less natural.
- After this event the assistant streams its answer via the normal content channel; the timeline auto-collapses once `message.content !== ''`.

---

## Sequence example

For a query like *"Ўзини ўзи ўлдиришга ундаш жинояти..."*:

1. `reasoning` – "The user is asking about Article 103-1 of the UzCrim Code..."  *(done in 0.2s)*
2. `knowledge_search` – query="Article 103 incitement to suicide", 6 items  *(1.3s)*
3. `reasoning` – "I should look up the actual current text..."  *(0.1s)*
4. `knowledge_search` – query="Plenum 2017 ruling", 8 items  *(0.9s)*
5. `summary` – "Organized comprehensive legal analysis of Uzbek criminal code provisions"  *(total 4.2s)*
6. Assistant streams the final answer.

The UI renders steps 1–4 as a vertical timeline with stagger animations; step 5 becomes the collapsed header when the answer starts streaming; clicking the header re-expands everything.

---

## Backward compatibility

Existing minimal events still render — the legacy path:

```jsonc
{ "type": "status", "data": { "description": "🔍 So'rov tahlil qilinmoqda...", "done": false } }
```

continues to display in the default branch of `StatusItem.svelte`. The crawler-lexuz repo should migrate fully to the structured events above; the fallback exists only to avoid breaking older client/server pairs during rollout.

---

## Open questions for crawler-lexuz

- How will the summary LLM call be configured (which model, prompt template, max tokens)? Should be deterministic enough that cached responses help.
- Token budget for `description` in `summary` events — target ≤80 chars to fit in the collapsed header without truncation.
- Should `snippet` be the raw Qdrant chunk text or a model-trimmed extract? Raw is fine for v1 since it isn't displayed; trim later when v2 UI lands.
