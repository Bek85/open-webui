# Phase 01: offline encyclopedia

**Context:** `deploy/encyclopedia/README.md`, `deploy/encyclopedia/workspace_tool.py`, `docs/legal-fast-path-routing.md`
**Priority:** high. **Status:** in progress (2026-09-09).

## Overview
Replace "web search" with local Wikipedia dumps (Uzbek maxi 3.7 GB, Russian nopic
14 GB) served by kiwix-serve; exposed as tool `search_encyclopedia` and as a
reader at `/wiki/` for users.

## Key insights
- kiwix-serve gives OpenSearch XML search and raw article HTML; book ids are ZIM basenames.
- Uzbek Wikipedia is Latin-script; Uzbek Cyrillic queries are routed to `uz` by letters ў қ ғ ҳ.
- Tool selection for "general" questions is still free model choice; measure it.

## Requirements
- Works with no internet for users; host downloads dumps.
- Answers cite reader URLs; native source cards from `citations`.
- Unavailable service degrades to an explicit caveat, never a fabricated citation.

## Related code
- Modify: `deploy/docker-compose.yml` (kiwix service, env), `ai-infra/nginx/default.conf` (`/wiki/`), `deploy/native_assistant/manage.py` (prompt composition), `system.txt`, UI captions.
- Create: `deploy/encyclopedia/{workspace_tool.py,instructions.txt,manage_encyclopedia.py,README.md,tests/}`.

## Steps / todo
- [x] Download dumps; probe kiwix API on a tiny dump.
- [x] Tool, tests, instructions, installer, compose, nginx, captions.
- [x] Start kiwix with the Uzbek dump; reload nginx; activate tool; refresh prompt.
- [x] Probe 10 general questions: free choice 4/8; added `wiki` route with server-side lookup (classifier 18/20).
- [ ] Re-probe after deploy: expect >= 8/10 with the article attached.
- [ ] Add the Russian dump when downloaded; rebuild/cut over WebUI for captions; commit.

## Success criteria
Tool fires on >= 8/10 factual questions in the probe set; answer links open in the reader; legal questions still route to LexUz.

## Risks
Tool selection flakiness (mitigation: phase 02 category router); dump refresh needs a compose edit (documented).

## Security
kiwix container read-only, no published port, no capabilities; XML parsed with defusedxml; only internal URL reachable by WebUI.
