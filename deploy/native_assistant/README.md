# Native ProkuraturaAI rollout

The unified assistant uses Open WebUI's native tool loop and Qwen's structured
tool calls. The existing LexUz and Bosh prokuror buyruqlari services remain the
specialist researchers. They receive a focused text question, not Open WebUI's
multimodal messages, full file contents, tool messages or conversation history.

`legal_research.py` is installed as a Workspace Tool, with two functions. It signs
the requesting user's identity using the existing `MCP_AUTH_SECRET` contract.
The prosecutor service remains the authorization boundary; denied requests are
not retried against another service. The adapter forwards research-timeline
events and returns the specialist answer with its original bibliography. The
opt-in native citation contract (`self.citation = True`, returned `citations`
array) turns bibliography links into native source cards and numbered citation
context. Search hits alone are not promoted to cited evidence.

Public model/tool access uses `principal_type=user, principal_id=*`, meaning
signed-in users. `anyone` means anonymous sharing and is stripped by these APIs.
The main model's `requiredToolIds` are merged server-side for UI requests, with
normal per-user access checks, so stale browser selections cannot omit research.
API/task requests without a UI session do not receive hidden required tools.
Display captions are localized independently of stable function identifiers.

Document reading uses Open WebUI's automatic extracted/retrieved file context
(`file_context=true`). This grounds the initial answer in document content even
when the model does not choose a file-reading tool. A live smoke test caught
that omission with optional native file tools, so automatic context is enabled.
Legal services still receive only the focused question formulated by the legal
tool, never the attachment-enriched message array. Whole-document coverage is
not implied by retrieved excerpts. Other built-in tool categories are disabled
for this initial rollout, except time utilities. File generators are not installed.

## Image limitation

On 2026-09-08 the model server accepted native tool calls but rejected the
synthetic image probe with `At most 0 image(s) may be provided in one prompt`.
Its launch script sets `--limit-mm-per-prompt '{"image": 0}'` and documents the
HPU vision path as untested. Vision stays disabled in the Workspace Model.
Enabling it requires separately validating and restarting the shared model
server, then updating the capability and prompt. Do not just toggle the UI flag.

## Restore point for this rollout

- Code: local git tag `restore/native-assistant-20260908`, commit `d0f559669`.
- Image: `openwebui/open-webui:restore-native-20260908`.
- Consistent SQLite backup and API exports:
  `/app/backend/data/restore-points/native-assistant-20260908-01` in the persistent
  WebUI volume, also copied to `deploy/restore-points/native-assistant-20260908-01`
  on the host. The SQLite integrity check passed before any model changes.
- Backup directories are private and ignored by git. They contain credentials
  and user data; do not publish them. The full database snapshot is emergency
  recovery only, not the normal rollback mechanism.

Open WebUI's `/models/export` excludes base-model overrides in this version;
`all-models.json` explicitly includes those overrides and their access grants.

## Deployment

Run from the fork's `custom/main` branch. `main` is reserved for upstream sync.
The tool and model settings live in the persistent database, so an image rebuild
alone neither installs nor removes them. `manage.py` calls authenticated local
admin APIs; tokens and connection keys are never printed.

```sh
docker cp deploy/native_assistant/. open-webui:/tmp/native-assistant-20260908/
docker exec -e PYTHONPATH=/app/backend -w /app/backend open-webui \
  python /tmp/native-assistant-20260908/manage.py inventory
```

For a fresh rollout, first run `snapshot --restore-dir <new-private-directory>`,
then `stage --restore-dir <that-directory>`. Stage creates an admin-only canary
and tool, and enables the existing hidden direct base model for administrators
only. No real chat is modified. Run the regression tests and canary probe:

```sh
docker exec -w /tmp/native-assistant-20260908 open-webui \
  python -m unittest -v test_legal_research
docker exec -e PYTHONPATH=/app/backend -w /tmp/native-assistant-20260908 open-webui \
  python -m unittest -v test_tool_citations test_manage
docker exec -e PYTHONPATH=/app/backend -w /app/backend open-webui \
  python /tmp/native-assistant-20260908/probe.py workflow
```

The workflow uses temporary websocket chats and a generated PDF, which is
deleted afterward. It tests greeting, law research, PDF reading after a legal
turn, and document-plus-law comparison. `probe.py capabilities` also tests the
underlying image endpoint; it is expected to fail until vision is enabled.

`probe.py access` checks that the real prosecutor service returns 403 for a
signed unprivileged identity. `probe.py prosecutor` tests authorized native
research without printing the internal answer. The pre-activation selective
rollback and restaging were also exercised successfully.
`probe.py visibility` checks model/tool visibility through read-only API calls
as a non-admin account. Chat smoke tests deliberately omit client `tool_ids` to
exercise server-side required-tool binding.

Build and recreate **only** `open-webui` with the standard compose deployment.
This supplies the host-gateway alias needed for RAG and the provider
`exclude_model_ids` support. Do not restart the pipelines or shared model server.
After the canary passes:

```sh
docker exec -e PYTHONPATH=/app/backend -w /app/backend open-webui \
  python /tmp/native-assistant-20260908/manage.py activate \
  --restore-dir /app/backend/data/restore-points/native-assistant-20260908-01
```

Activation preserves `router_pipeline`, the model ID in existing chats, as a
Workspace preset pointing to direct `ProkuraturaAI`. It excludes only the old
router from pipeline-provider discovery. Dynamic specialist discovery and its
`pipeline` metadata are preserved, including the unrelated LexUz v7 model.
**Do not replace provider discovery with static `model_ids`: doing that drops
the metadata needed to forward user identity to the legacy pipelines.** Preserve
the `exclude_model_ids` setting when editing those provider connections.

Refresh the browser after activation to load the new default tools. Existing
chats and file attachments are retained. Dedicated LexUz/Prosecutor models keep
their existing attachment restrictions; use ProkuraturaAI for mixed tasks.

## Selective rollback (preserves new chats and uploads)

```sh
docker cp deploy/native_assistant/. open-webui:/tmp/native-assistant-20260908/
docker exec -e PYTHONPATH=/app/backend -w /app/backend open-webui \
  python /tmp/native-assistant-20260908/manage.py rollback \
  --restore-dir /app/backend/data/restore-points/native-assistant-20260908-01
```

This restores provider settings and the original direct-base override, and
removes only the newly created native model presets/tool. It refuses to replace
provider settings that changed independently after rollout. Review concurrent
model/tool edits before using rollback. The backend change is dormant without
`exclude_model_ids`; reverting the image is normally unnecessary. If necessary,
retag the restore image as `openwebui/open-webui:latest` and recreate only WebUI
with `--no-build`; never overwrite the live database while WebUI is running.
