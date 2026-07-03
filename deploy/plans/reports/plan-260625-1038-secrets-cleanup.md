# Secrets Cleanup Plan (2026-06-25)

Planning only — no rotation executed. Rotations are outward-facing; the operator runs them.

## Good news first
- **No `.env` is in git history** (checked `git log --all -- .env` in all 4 repos = 0 commits). Secrets are on-disk only (gitignored), NOT leaked into VCS. So this is hygiene/dedup, not an incident.

## Secrets inventory (redacted) + locations
| Secret | Where | Issue |
|---|---|---|
| NIM/LLM API key | `ocr-service/.env`, `openwebui/deploy/.env` (as `OPENAI_API_KEY` ×2 + `CLASSIFIER_KEY`) | **same key ×3**, 2 repos, 2 names → rotation drift |
| `PIPELINES_API_KEY` | `openwebui/deploy/.env`, `ocr-service/.env` | duplicated across repos |
| `UZBEK_TTS_TOKEN` | `openwebui/deploy/.env`, `ocr-service/.env` | duplicated across repos |
| `POSTGRES_PASSWORD` | `ocr-service/.env` (also inline in `OCR_SERVICE_DATABASE_URL` DSN) | same secret in 2 forms |
| `MINIO_ROOT_PASSWORD` / `MINIO_SECRET_KEY` | `ocr-service/.env` | two vars, one credential |
| `OAUTH_CLIENT_SECRET` | both `.env` | duplicated cross-repo |
| `NEO4J_AUTH` / `NEO4J_PASSWORD` | `legal-rag/.env` | placeholder `changeme`; expressed twice |
| legal-rag JWT (DeepInfra) | `legal-rag/.env` line ~39 (commented) | dead secret, `exp`≈2026-06-30 (maybe still valid) |

## Risks
1. **Duplication → rotation drift:** the NIM key lives in 3 places under 2 names; rotating one misses the others → silent auth failures.
2. **Cross-repo `.env` pollution:** `ocr-service/.env` carries openwebui-only secrets/vars (`PIPELINES_API_KEY`, `UZBEK_TTS_TOKEN`, `LEX_UZ_RAG_URL`…) — wrong owner, more copies to rotate.
3. **Dead secrets:** commented JWT in legal-rag — remove; rotate if ever real.
4. **Weak/placeholder:** `NEO4J_AUTH=neo4j/changeme`.
5. **No central secret store:** all plaintext `.env`; fine at this scale but no rotation/audit story.

## Remediation plan (priority order)
1. **De-dup shared secrets → one place** (do this first; enables clean rotation):
   - Shared across repos: NIM key, `PIPELINES_API_KEY`, `UZBEK_TTS_TOKEN`, `OAUTH_CLIENT_SECRET`.
   - Put each in ONE file the consumers read. Two viable patterns:
     - (a) **Shared `/home/user/ai/secrets.env`** (chmod 600, gitignored), loaded via `--env-file` alongside the per-repo `.env`. Mirrors the `endpoints.env` design.
     - (b) **Docker secrets** (compose `secrets:` + `/run/secrets/*`) — better isolation, but apps must read files not env (code change). Heavier.
   - Recommendation: **(a) for now** (KISS, matches endpoints pattern); revisit (b)/SOPS if audit needs grow.
2. **Remove cross-repo pollution:** delete openwebui-only vars from `ocr-service/.env` (`PIPELINES_API_KEY`, `UZBEK_TTS_TOKEN`, `LEX_UZ_RAG_URL`, `PROSECUTOR_RAG_URL`, `DEFAULT_MODELS`) after confirming ocr code doesn't read them (audit says it doesn't).
3. **Collapse dual forms:** derive `OCR_SERVICE_DATABASE_URL` from `POSTGRES_*` parts (or keep DSN and drop the discrete dupes); pick one Neo4j form (`NEO4J_AUTH` xor `NEO4J_USERNAME`+`NEO4J_PASSWORD`); one MinIO credential var.
4. **Remove dead secrets:** delete the commented JWT block in `legal-rag/.env`.
5. **Rotate** (operator; after de-dup so each rotates in one place): NIM key, DB pw, MinIO keys, OAuth secret, pipelines key, TTS token, Neo4j (`changeme` → strong).
6. **Hardening:** `chmod 600` all `.env`; confirm `.gitignore` covers `.env`, `secrets.env`, `*.env` (not `.env.example`); add a pre-commit secret scan (gitleaks/trufflehog) so a future `.env` can't be committed.

## Rotation checklist (per secret)
For each: (1) generate new value, (2) update the single source, (3) recreate consuming services, (4) verify (auth works / health green), (5) invalidate old value at the provider.
- NIM key → consumers: ocr-api, celery, openwebui (LLM + classifier). Verify a chat + an OCR job.
- DB pw → postgres + ocr-api/celery/alembic. Verify migrations + queries.
- MinIO → minio + celery (S3). Verify upload.
- TTS token → open-webui. Verify Read-Aloud.
- Pipelines key → pipelines + open-webui. Verify RAG route.

## Unresolved
- Confirm with operator: adopt shared `secrets.env` (pattern a) vs a real secret store (SOPS/Vault)?
- Is the legal-rag JWT still live (rotate) or fully dead (just delete)?
