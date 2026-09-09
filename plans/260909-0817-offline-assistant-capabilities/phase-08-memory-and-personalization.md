# Phase 08: memory and personalization

**Context:** Open WebUI memory feature (offline), Workspace prompts.
**Priority:** low. **Status:** planned.

## Overview
Seed per-user memory with role, region, department and preferred script so
drafts and answers are right the first time; add Workspace prompt templates for
standard document types.

## Steps
1. Enable memory for the main model; seeding script from the user directory (admin-run).
2. Prompt templates: letter, notice, protest, submission (uz Latin / uz Cyrillic / ru).
3. Probe: first-draft quality with and without memory on 10 requests.

## Success criteria
Fewer follow-up corrections per draft on the probe set; users can see and delete their memory entries.

## Risks
Personal data in memory: keep to role/region/script, never case data.
