# Private file generation — initial release

The isolated renderer produces **DOCX, PDF and XLSX** from data-only native tool
calls. It has no model credentials, host mounts, Docker socket, public ports or
outbound network. It does not execute model-written Python, accept file paths,
download resources, edit uploads or modify the research pipelines.

Supported documents: headings, paragraphs, simple lists, emphasis, HTTP(S)
source links and small Markdown tables. PDFs embed DejaVu fonts for Uzbek
Latin/Cyrillic and Russian. DOCX uses editable Word paragraphs/tables and Arial.
Excel supports up to 5 sheets, 20 columns/sheet, 1000 rows/sheet and 10000 cells
total. Strings, including formula-like strings, are stored as literal text;
formulas, macros, external workbook links and exact template reproduction are
not supported. HTML/CSV/PPTX are deferred, not silently substituted.

## Security and retention

WebUI signs method, path, owner, timestamp and body hash with a dedicated key.
The renderer rejects stale/invalid signatures; the model never receives the key
or chooses the owner. Downloads go through WebUI login and are checked against
the same owner in the renderer, including when a chat/link is shared. Even a
different administrator cannot download someone else's artifact through this
route. URLs contain no bearer credentials. Responses are attachment-only and
`private, no-store`.

Generated files expire **30 days** after creation. An hourly cleanup removes
expired artifacts in the dedicated `generated_files` volume only. Existing
uploads, chats and research data are untouched. Per-user limit: 100 retained
artifacts; total stored artifact quota: 2 GiB; output limit: 10 MiB/file; request
limit: 512 KiB. Two render jobs can run concurrently. CPU/memory/PID limits and
a read-only root filesystem bound the renderer. No content is logged by it.

## Build and tests

```sh
docker build --target test -t openwebui/file-generation:test deploy/file_generation
docker run --rm --network none openwebui/file-generation:test
docker compose -f deploy/docker-compose.yml build file-generation
```

The signing key is a 32-byte random file at
`deploy/file_generation/secrets/signing.key` (git-ignored and excluded from build
context). Its parent directory must be mode 0700; the key is readable by the
non-root service through a read-only Docker secret mount. Back up this key and
the dedicated volume securely. Do not replace the key during normal deploys.

Deploy only `file-generation` and `open-webui`; do not restart Qwen or pipelines.
The WebUI image must contain `routers/generated_files.py`, and WebUI must join
the private renderer network and mount the key. The Workspace Tool is stored in
WebUI's database and must be installed separately; rebuilding alone does not
install it.

## Staged rollout

Preserve the current code/image and a WebUI database snapshot first. Copy this
directory and `deploy/native_assistant` into WebUI's `/tmp`, adding the latter
to `PYTHONPATH`. Run `manage_files.py stage --restore-dir <new-private-path>`.
It backs up the current main model and creates a private admin canary, leaving
the public model unchanged. Test all three formats, ordinary chat, research-tool
availability, owner download and another user's denied download.

Only after those checks pass, run `manage_files.py activate --restore-dir <same-path>`.
This adds the file tool to the current model's tool IDs/required IDs and appends
instructions, preserving existing model parameters, metadata, grants and legal
tools. Do not rerun the earlier native-assistant initial activation to update
this model; that would replace later additions.

Rollback: restore the saved `main-model.json` through the model-update API after
checking for subsequent edits, then make the file tool private. Retain the
renderer/download route until existing generated downloads expire if desired.
Do not restore the entire database or delete the artifact volume to roll back
the model feature.
