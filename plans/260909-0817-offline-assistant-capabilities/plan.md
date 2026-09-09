# Offline assistant capabilities for ProkuraturaAI

Goal: close the gap to Claude/ChatGPT/Gemini for an offline, internal audience by
adding grounded capabilities around the existing 27B model, one tool family at a
time, each with a routing test before it goes live.

Context (measured 2026-09-09): free model tool choice hits ~60% on implicit
requests at any temperature; deterministic routing (temperature-0 classifier,
`backend/open_webui/utils/legal_fast_path.py`) is the pattern that works.
Every phase below ships with a probe suite so this stays measurable.

| Phase | Scope | Status |
|---|---|---|
| [01](phase-01-offline-encyclopedia.md) | Offline encyclopedia (kiwix + Wikipedia uz/ru) as a tool and reader | In progress |
| [02](phase-02-routing-test-suite-and-category-router.md) | Routing test suite + per-category deterministic router | Planned |
| [03](phase-03-document-intelligence.md) | Long-document summarization, comparison, structure-preserving translation | Planned |
| [04](phase-04-legal-calculators.md) | Deterministic legal calculators (BHM by date, procedural deadlines, fine ranges) | Planned |
| [05](phase-05-code-interpreter-and-spreadsheet-analytics.md) | Offline code interpreter (Pyodide) for calculations and uploaded spreadsheets | Planned |
| [06](phase-06-vision.md) | Image input (scans, photos, screenshots) after model-server validation | Planned |
| [07](phase-07-voice.md) | Local speech-to-text and text-to-speech, Uzbek quality gate | Planned |
| [08](phase-08-memory-and-personalization.md) | Role/region/department memory seeding for better first drafts | Planned |

Dependencies: 02 before 03-05 (routing must be measurable before more tools);
06 needs a validated vLLM restart (shared model server, downtime window); 07
depends on an Uzbek recognition quality test, not on any other phase.

Excluded from this plan: image generation (low value for this audience).

## Side note: integrations with internal systems (later)

Not scheduled now. When the time comes, each system (e-hujjat document flow and
others) gets its own MCP or OpenAPI tool server behind the same signed-identity
contract the legal tools use (`MCP_AUTH_SECRET`, HMAC v1 headers), so the target
system enforces per-user permissions itself. Read-side first (document status,
inbox, history); write actions (register, assign, draft-and-send) only through a
single preview-confirm-execute-audit pattern defined once and reused. Route with
a category classifier, never free model choice. Read-only analytics over internal
databases (text-to-SQL with a schema allowlist) belongs to the same wave.
