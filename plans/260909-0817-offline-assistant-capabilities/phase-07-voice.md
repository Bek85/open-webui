# Phase 07: voice

**Context:** Open WebUI local STT/TTS engines; no external APIs allowed.
**Priority:** low-medium. **Status:** planned (gated by a quality test).

## Overview
Speech input for officers and read-aloud answers, using local Whisper for
speech-to-text and a local TTS engine.

## Steps
1. Quality gate: transcribe 30 Uzbek and 30 Russian sentences with faster-whisper (large-v3) on CPU/HPU; require >= 90% word accuracy for Uzbek before enabling.
2. Deploy STT container; enable audio input for the main model.
3. TTS only if a usable Uzbek voice exists; otherwise Russian only.

## Success criteria
Uzbek dictation usable in practice (measured accuracy), latency under 5 s for a 15-second clip.

## Risks
Uzbek recognition quality is the unknown; do not promise voice before the gate passes.
