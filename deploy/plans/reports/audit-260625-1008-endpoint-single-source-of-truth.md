# Endpoint Single-Source-of-Truth — Audit & Design (2026-06-25)

Scope: ai-infra, legal-rag, ocr-service, openwebui (deploy), vllm-gaudi. Read-only audit done by 3 parallel agents.

## TL;DR
Intra-stack services (postgres/redis/minio/qdrant/docling) already use clean docker-DNS — leave them.
The pain is the **cross-cutting, host-served endpoints** (LLM, embedding, reranker, RAG, TTS): addressed 3–4 different ways, duplicated 6–9× each, with stale templates and inconsistent var names. Fix = one shared file + one addressing style + one var name per endpoint.

## The 5 shared endpoints + current chaos
| Endpoint | Authoritative bind (vllm-gaudi) | Addressed as (consumers) | Copies |
|---|---|---|---|
| LLM `ProkuraturaAI` | host **:8000** (`vllm-gaudi/docker-compose.yml` entrypoint `-p 8000`) | `172.17.0.1:8000` (ocr,owui,router_pipeline), `172.18.35.123:8000` (legal-rag docs+code), `host.docker.internal:8001` ❌wrong-port (legal .env.example), `vllm:8000` ❌dead (ocr config.py) | 6+ |
| Embedding `KaLM` (TEI) | host **:8003** (`--port 8003`) | `172.18.35.123:8003` ×8 (legal-rag compose×4 + code×3 + comment), `host.docker.internal:8003` (ai-infra prometheus), `embedder:80` ❌stale (legal .env) | 9+ |
| Reranker `gte` (TEI) | bridge **`reranker:80`** | `reranker:80` (good DNS) but a Python constant in `cross_encoder_reranker.py:13`, not env-driven | 2 |
| RAG stream (mcp-server) | host **:4040** | `172.18.35.123:4040` (ocr,owui,router), `host.docker.internal:4040` (lexuz_pipeline, prosecutor_pipeline) | 6+ |
| TTS (Uzbek, **other box**) | `172.18.35.124:8000` | inline literal in `openwebui/deploy/docker-compose.yml:52` | 2+ |

## Cross-cutting smells
- 3–4 addressing styles per service (LAN IP / docker0 gw `172.17.0.1` / `host.docker.internal` / dead DNS).
- Stale templates: `legal-rag/.env.example` → dead `embedder:80`, wrong LLM port 8001, `EMBEDDING_DIM=4096` vs live **3840**, Qdrant collection names missing `_kalm`. Won't run from template.
- Duplicate var names for one value: LLM `OPENAI_API_BASE_URL`/`CLASSIFIER_BASE_URL`; docling `DOCLING_BASE_URL`/`DOCLING_URL`; redis `REDIS_URL`/`CELERY_BROKER_URL` (latter likely dead); OIDC signout ×2; Neo4j creds ×2.
- Cross-repo `.env` pollution: `ocr-service/.env` carries openwebui-only vars (`LEX_UZ_RAG_URL`, `PROSECUTOR_RAG_URL`, `DEFAULT_MODELS`, `UZBEK_TTS_TOKEN`).
- vllm-gaudi: every port hardcoded ×3 (entrypoint + script default + healthcheck); no `.env` at all.

## Design — one source of truth
### Principles
1. **One addressing style** for host-served models: `host.docker.internal:<port>` everywhere + `extra_hosts: ["host.docker.internal:host-gateway"]` on each consumer (prometheus/pipelines already do this). Portable across boxes (you sync to the 8gpu host) — no per-machine IP edits.
2. **One var name** per logical endpoint, identical across all repos.
3. Shared values in ONE file; repo `.env` only for repo-specific/secret values.
4. Don't touch good intra-stack DNS endpoints (YAGNI).

### Canonical file: `/home/user/ai/endpoints.env` (host-level, gitignored like other .env; commit `endpoints.env.example` in ai-infra)
```dotenv
# Cross-cutting model/service endpoints — SINGLE SOURCE OF TRUTH.
# Host-served models reached via host.docker.internal (portable across hosts).
LLM_ENDPOINT=http://host.docker.internal:8000/v1
LLM_MODEL=ProkuraturaAI
EMBEDDING_ENDPOINT=http://host.docker.internal:8003/v1
EMBEDDING_MODEL=/data/KaLM-Embedding-Gemma3-12B-2511
EMBEDDING_DIM=3840
RERANKER_ENDPOINT=http://reranker:80        # bridge DNS, stays
RAG_BASE_URL=http://host.docker.internal:4040
TTS_ENDPOINT=http://172.18.35.124:8000/v1   # separate box → real remote addr

# --- PUBLIC ingress (edge only) — domain cutover lives here, one place ---
# Today dev-accessed at http://172.18.35.123:8080; production = https://ai.prokuratura.uz (nginx SSL).
PUBLIC_BASE_URL=https://ai.prokuratura.uz   # used by WEBUI_URL, OAuth redirect/signout, CORS, nginx server_name
OIDC_PROVIDER_URL=https://id.prokuratura.uz
```
Secrets NOT here (see hygiene).

### Wiring per repo — mechanism (corrected)
Docker Compose `${...}` interpolation reads ONLY the project `.env` (auto-loaded), the shell, or `--env-file` — **not** a service-level `env_file:`. And each app expects its own var name. So:

**Default (robust, zero plumbing):** put the canonical vars in each repo's own `.env`, map to the app's var in compose `environment:`:
```yaml
services:
  <svc>:
    extra_hosts: ["host.docker.internal:host-gateway"]
    environment:
      - EMBEDDING_BINDING_HOST=${EMBEDDING_ENDPOINT}   # app var = ${canonical from .env}
      - EMBEDDING_REQUEST_MODEL=${EMBEDDING_MODEL}
```
```dotenv
# each repo's .env (single source within the repo; same NAMES across all repos)
EMBEDDING_ENDPOINT=http://host.docker.internal:8003/v1
EMBEDDING_MODEL=/data/KaLM-Embedding-Gemma3-12B-2511
```
Cross-repo "single source" = identical var NAMES everywhere + a committed canonical reference `ai-infra/endpoints.env.example`. Changing an endpoint = edit each repo's `.env` (one obvious line, greppable) — vs today's 6–9 scattered literals.

**Optional upgrade to ONE physical file:** add `--env-file /home/user/ai/endpoints.env --env-file .env` to each repo's compose invocation (deploy.sh/redeploy.sh). Gives a literal single file but requires editing the deploy scripts (and ocr-service still uses compose v1, single `--env-file` only). Defer unless wanted.
Then replace literals with `${...}`:
- legal-rag ×4 services: `EMBEDDING_BINDING_HOST=${EMBEDDING_ENDPOINT}`, `EMBEDDING_REQUEST_MODEL=${EMBEDDING_MODEL}`; drop inline IPs + stale .env.example lines.
- openwebui deploy: `AUDIO_TTS_OPENAI_API_BASE_URL=${TTS_ENDPOINT}`.
- ocr-service: `OPENAI_API_BASE_URL=${LLM_ENDPOINT}`, `LEX_UZ_RAG_URL=${RAG_BASE_URL}/lex_uz/stream`, etc.
- code defaults (router_pipeline.py, legal-rag clients.py, cross_encoder_reranker.py) → read the env var, default to the SAME host.docker.internal value.

### Why host.docker.internal (not LAN IP / 172.17.0.1)
- Portable: identical on every box → no per-host IP edits.
- Kills the 3-way drift.
- `172.17.0.1` (docker0 gw) only works on default bridge; `host.docker.internal`+host-gateway works on any user network (ai_network etc.).
- Exception: TTS is a different machine → keep its real address (centralized as `TTS_ENDPOINT`).

### Internal vs Public — and the ai.prokuratura.uz / SSL cutover
Two categories, two variables — never mix them:
| | Internal (service→service) | Public (user→edge) |
|---|---|---|
| Examples | LLM, embedding, reranker, RAG, TTS | the chat UI itself |
| Var | `*_ENDPOINT` (host.docker.internal / DNS) | `PUBLIC_BASE_URL` |
| Today | `host.docker.internal:<port>` | `http://172.18.35.123:8080` (direct) |
| Production | unchanged | `https://ai.prokuratura.uz` via nginx SSL |

- **Do NOT** point internal model calls at `ai.prokuratura.uz` — that hairpins a local call out through public DNS + the SSL edge and couples internal health to the public cert/DNS. Internal stays `host.docker.internal`, which is already domain-/IP-independent → the cutover touches **zero** internal config.
- Ingress already exists: `ai-infra/nginx/default.conf` has `listen 443 ssl`, `server_name ai.prokuratura.uz`, `upstream open-webui:8080`. Cutover = (1) DNS A record `ai.prokuratura.uz` → public IP, (2) TLS cert (Let's Encrypt/provided) wired into nginx, (3) flip `PUBLIC_BASE_URL` and consume it in: open-webui `WEBUI_URL`, OAuth `redirect`/`signout` URIs, `CORS_ALLOW_ORIGIN`, nginx `server_name`. All these are currently scattered literals → centralize to `PUBLIC_BASE_URL`.
- Result: pushing to production = set DNS + cert once, flip one var. No service-endpoint churn.

## Migration plan (behavior-preserving, staged)
Per repo: edit → `docker compose config` BEFORE vs AFTER must resolve identical → recreate only if a value actually changed → verify health. Rollback = revert compose/.env (no data impact).
Order (lowest risk first):
1. openwebui deploy — TTS var only (cosmetic; resolves identical).
2. ocr-service — LLM/RAG vars.
3. legal-rag — embedding ×4 (biggest; touches live prosecutor/lexuz RAG).
4. vllm-gaudi — optional: introduce `.env` for the bind ports.
5. ai-infra — fix prometheus TEI scrape (`:8003` → `:9301`).

## Out of scope, flagged separately
- **SECURITY (high):** secrets committed plaintext in 4 `.env` (NIM key ×3, DB/MinIO/OAuth/TTS/pipeline keys); JWT in legal-rag/.env (commented, `exp`≈2026-06-30). Rotate + secret store.
- vllm-gaudi stale: README TP=8 vs real TP=4; cron `COMPOSE_DIR=/home/user/ocr-server/vllm-plugin` wrong path; orphan `start_vllm_embedding.sh`; prometheus scrapes wrong TEI metrics port.

## Unresolved
- Home for `/home/user/ai/endpoints.env` in git: recommend untracked host file + `endpoints.env.example` in ai-infra.
- legal-rag/ocr-service live `.env` not fully readable (secrets) — confirm exact current values before swap.
