# Phase 05: offline code interpreter and spreadsheet analytics

**Context:** `ENABLE_CODE_INTERPRETER: false` in `deploy/docker-compose.yml`; Open WebUI supports Pyodide (browser) and Jupyter (server).
**Priority:** medium. **Status:** planned.

## Overview
Let the model compute: statistics over an uploaded Excel/CSV, unit and date
math, charts. Pyodide runs in the browser and works offline once its assets are
bundled into the image; Jupyter is the server-side alternative with stronger
isolation needs.

## Requirements
- Fully offline: Pyodide wheels and packages vendored in the image, no CDN.
- Disabled for API callers; enabled per model capability.

## Steps
1. Vendor Pyodide assets; enable `ENABLE_CODE_INTERPRETER` for the main model only.
2. Probe: 10 spreadsheet questions (sums, group-bys, a chart).
3. Decide on Jupyter only if Pyodide limits (pandas size, runtime) are hit.

## Success criteria
Spreadsheet questions answered with computed numbers, not estimates, in under 30 s.

## Risks
Bundle size and first-load time; guard with lazy loading.
