# Phase 04: deterministic legal calculators

**Context:** specialist "calculation guard" about BHM values (legal-rag prompts), time tools already enabled.
**Priority:** medium-high. **Status:** planned.

## Overview
Small, exact tools the model cannot get wrong: base calculation value (BHM) by
date, monetary thresholds expressed in BHM multiples, procedural deadline
arithmetic (working days, code-specific rules), fine ranges per article.

## Requirements
- Data tables versioned in the repo (`deploy/legal_calculators/data/*.json`) with source references and effective dates.
- Every result returns the table entry used so the answer can cite it.

## Related code
- Create: `deploy/legal_calculators/workspace_tool.py`, data files, tests.
- Modify: `system.txt` (use calculators instead of memory for amounts and deadlines), COMPANION_TOOLS.

## Steps
1. BHM table + `bhm_value(date)` and `amount_in_bhm(amount, date)`.
2. Deadline calculator with holiday calendar.
3. Fine ranges once article data is curated with the legal team.

## Success criteria
100% agreement with the curated tables on unit tests; specialist answers stop hedging on BHM.

## Risks
Table maintenance is a legal-team responsibility; make the data files the single source and document the update path.
