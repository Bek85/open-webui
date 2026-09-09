# Phase 06: vision (image input)

**Context:** `deploy/native_assistant/README.md` "Image limitation"; vLLM launched with `--limit-mm-per-prompt '{"image": 0}'` (`vllm-gaudi/start_vllm_qwen38.sh`).
**Priority:** medium. **Status:** planned.

## Overview
Photographed documents, screenshots and scans as chat input. The model is
multimodal but the shared server rejects images today; enabling it is a
model-server change with a restart window, then a capability flag and prompt update.

## Steps
1. Validate image inference on the HPU build in a drained window (`restart-vllm-prokuratura-drained.sh` pattern); measure throughput impact.
2. Enable `vision` capability on the main model; update `system.txt` (remove the "images disabled" rule); keep image turns on the native path (fast path already excludes them).
3. Probe with 10 document photos (uz/ru), compare with docling OCR output.

## Success criteria
No regression in text throughput above an agreed budget; photo questions answered without OCR round-trip.

## Risks
HPU vision path documented as untested; shared server downtime affects the specialist too.
