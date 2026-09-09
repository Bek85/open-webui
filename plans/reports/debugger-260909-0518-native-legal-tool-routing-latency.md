# ProkuraturaAI unified chat: legal tool not invoked + slow final answer

Date: 2026-09-09. Scope: `router_pipeline` preset (base `ProkuraturaAI`, vLLM Qwen3.8-27B, thinking off, `qwen3_xml` parser), Workspace tool `deploy/native_assistant/legal_research.py`, specialist = `legal-rag` mcp-server (:4040). No production changes made. Probe scripts left in container `open-webui:/tmp/na/`.

## Problem 1 — model answers legal questions from memory

Root cause: the model's *auto* tool choice is stochastic on implicit legal questions. Not a wiring bug: required tools bind server-side, specs reach vLLM (prompt ≈2.08K tokens, 6 functions), parser works.

Evidence (direct vLLM calls, production prompt + tool specs, 8 implicit Uzbek questions + 1 greeting):

| Configuration | Tool called |
|---|---|
| Production (thinking off, vLLM default temp 1.0) | 5/8 |
| temperature 0.2 | 2/8 and 1/8 (worse) |
| temperature 0.7 | 6/8 and 5/8 (same as production); queries 260-520 chars |
| enable_thinking=true | 8/8 but 300-600 thinking tokens (+15-30s), 2/8 empty `{}` args |
| system-prompt rule only | 5/8 |
| tool-description only | 5/8 |
| prompt rule + tool description + "one question <400 chars" | 8/8, 6/8, 5/8 (19/24) |

End-to-end through the real chat: "Aliment to'lamasa nima bo'ladi?" and "Pora berish uchun qancha jazo beriladi?" both answered from memory (20s / 40s); the second cited a fabricated article.

Degenerate mode: for some questions the model emits the user question verbatim and stops (raw `/v1/completions` on the exact rendered prompt: 3/6 samples, no `<tool_call>` tokens). Model-level, present at every temperature.

Secondary: when it does call the tool it rewrites the question into a 200-370 token compound query. The specialist then classifies `kazus`/`compound_query`, runs more branches (25s subtopic timeouts observed) and triggers its `stated_gap` addendum re-run.

## Problem 2 — long wait after sources are retrieved

Measured tool call for a simple implicit question (`tool_timing.py`):

| Phase | t |
|---|---|
| specialist retrieval done (15 sources) | 11s |
| specialist first token | 15s |
| specialist synthesis complete | 78s |
| `stated_gap` addendum: 2nd search + 2nd synthesis | 78s → 135s |
| tool returns (10.3K chars) | 135s |
| outer model re-prefill + re-generate (~25 tok/s single stream, prefix-cache hit 0%) | ≈ +40-70s |

Direct LexUz pipeline streams the specialist's tokens, so the user sees text at ~15s. The tool path hides everything until 135s and then generates the answer a second time. Production sample 04:45 UTC: specialist hit its 180s budget ("LLM hung mid-generation; emitting degraded fallback") because the addendum re-run started after a 61s synthesis.

Not causes: Open WebUI tool loop (fine), tool result size (10K chars), the 05:17 `ClientPayloadError` (manual `docker restart mcp-server`, not a crash).

## Recommendations

1. Routing must not depend on free model choice. Add a deterministic first-turn router: one temperature-0 one-word classification (reuse `router_pipeline.py` CLASSIFY_SYSTEM, already tuned) and force `tool_choice={"type":"function","function":{"name":"research_uzbek_law"}}` on the first iteration only (vLLM supports named tool_choice). Keep auto choice for document/greeting turns.
2. Still apply the prompt + tool-description changes (cheap, reduces misses and shortens queries): tool description "REQUIRED for any question whose answer depends on Uzbek law, incl. 'what should I do'/'what happens if'"; query = user's question as asked, <400 chars.
3. Latency: stop double synthesis for legal-only turns. Either (a) relay: tool streams specialist text into the chat via `__event_emitter__` `message` deltas and returns a short "already delivered" result so the outer model adds ≤2 sentences, or (b) hybrid: legal-only turns (classifier=legal, no attachment) proxy the specialist stream directly as the answer; tool path only for document+law comparisons. (b) gives parity with the direct pipeline (~15s to first text).
4. For tool-originated requests, mark them (header) and disable the specialist's `stated_gap` addendum / lower `RAG_STREAM_TOTAL_BUDGET_SEC`; saves 45-60s per call.
5. Set an explicit temperature (~0.6-0.7) on the preset for answer quality; vLLM currently samples the outer model at 1.0 (generation_config). Does not fix tool choice.

## Unresolved

- Whether Chat.svelte keeps tool-emitted `message` content once the native loop's `chat:completion` output arrives (decides relay vs hybrid).
- Whether the "echo" degenerate output is specific to this Qwen3.8-27B checkpoint/template; not reproducible with thinking on.
