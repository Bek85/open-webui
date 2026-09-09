# Phase 02: routing test suite and category router

**Context:** `plans/reports/debugger-260909-0518-native-legal-tool-routing-latency.md`, `backend/open_webui/utils/legal_fast_path.py`
**Priority:** high (foundation for every later tool). **Status:** in progress (suite shipped 2026-09-09; forced-tool mechanism pending).

## Overview
Turn today's ad-hoc probes into a repo-tracked suite and generalize the
temperature-0 classifier so each tool family (legal, encyclopedia, files, later
document tools) is selected deterministically, not by sampling.

## Requirements
- `deploy/native_assistant/routing_probes/` with one file per category of representative Uzbek Latin, Uzbek Cyrillic and Russian requests plus expected tool; runner reports per-category hit rate against the live model.
- Classifier prompt extended from lexuz/prosecutor/general to named categories; result forces `tool_choice` on the first model iteration for categories that map to a single tool, and the middleware strips it afterwards.
- Gate: no prompt/tool change ships below the recorded baseline.

## Related code
- Create: probe runner (Python, runs inside the WebUI container), category prompt.
- Modify: `legal_fast_path.py` (classification categories), tool loop in `utils/middleware.py` (one-shot `tool_choice`), README.

## Steps
1. [x] `deploy/routing_tests/`: 59 cases in five categories (three scripts), runner with `classifier` and `e2e` modes, `baseline.json` gate. Classifier baseline 1.00 in every category.
2. [ ] Grow cases from real (anonymized) chats as new request shapes appear.
3. [ ] Generic category -> forced tool mechanism (one-shot `tool_choice`, stripped after the first iteration) when the first new tool category (document flow) arrives; until then legal and encyclopedia routes are deterministic and file creation relies on model choice (3/3 in tests).

## Success criteria
>= 90% correct tool per category; greetings/writing never trigger a tool.

## Risks
Forced `tool_choice` on vLLM needs structured output enabled (it is); a misclassification is worse than no call, so keep "general" as the safe default.
