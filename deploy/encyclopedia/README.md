# Offline encyclopedia (kiwix-serve + Wikipedia ZIM dumps)

Users have no internet. General-knowledge questions ("who is", "what is",
places, history, science, definitions) are answered from local Wikipedia dumps
served by kiwix-serve, exposed to the model as the Workspace tool
`prokuratura_encyclopedia` (`search_encyclopedia`) and to users as a reader at
`https://ai.prokuratura.uz/wiki/`.

## Pieces

| Piece | Where |
|---|---|
| ZIM dumps | `/home/user/ai/kiwix/zim/` on the host (bind-mounted read-only) |
| kiwix-serve | `kiwix` service in `deploy/docker-compose.yml`, no published port, `--urlRootLocation /wiki` |
| reader for users | nginx `location ^~ /wiki/` in `ai-infra/nginx/default.conf` (upstream `kiwix`) |
| tool code | `workspace_tool.py` (installed into the WebUI database) |
| prompt text | `instructions.txt`, appended by `native_assistant/manage.py refresh` when the tool is bound |
| config | `ENCYCLOPEDIA_KIWIX_URL`, `ENCYCLOPEDIA_PUBLIC_URL`, `ENCYCLOPEDIA_BOOKS` on the `open-webui` service |

Book ids are the ZIM file basenames (kiwix-serve names books that way when
files are passed on the command line). `ENCYCLOPEDIA_BOOKS` is
`language:book-id` pairs, e.g. `uz:wikipedia_uz_all_maxi_2026-07,ru:wikipedia_ru_all_nopic_2026-01`.

The tool searches every configured book (query script decides the order:
Latin or Uzbek Cyrillic letters prefer `uz`, other Cyrillic prefers `ru`),
returns titles, snippets and reader URLs, and includes the text of the top
article (6000 characters by default). Returned `citations` become native
source cards. kiwix endpoints used: `/search?books.name=…&pattern=…&format=xml`
and `/raw/<book>/content/<path>`.

## Routing

The temperature-0 route classifier (`backend/open_webui/utils/legal_fast_path.py`)
has a `wiki` class for general-knowledge questions. For those turns the backend
calls the tool itself with the user's question and attaches the article and
snippets as cited context before the model answers
(`backend/open_webui/utils/encyclopedia_context.py`). The model can still call
the tool on its own for follow-ups. Measure with the routing suite
(`deploy/routing_tests/`, category `encyclopedia`, modes `classifier` and `e2e`).

## Dumps in use

| Language | File | Size | Notes |
|---|---|---|---|
| Uzbek | `wikipedia_uz_all_maxi_2026-07.zim` | 3.7 GB | with images |
| Russian | `wikipedia_ru_all_nopic_2026-01.zim` | 14 GB | text only; `_maxi` (38 GB) has images |

Source: `https://download.kiwix.org/zim/wikipedia/` (host has internet; users do not).

## Updating dumps

1. Download the new file into `/home/user/ai/kiwix/zim/` (`curl -C -` resumes).
2. Add it to the `kiwix` service `command` and to `ENCYCLOPEDIA_BOOKS` in
   `deploy/docker-compose.yml`; remove the old file from both.
3. `docker compose -f deploy/docker-compose.yml up -d kiwix open-webui` (recreates both;
   open-webui only needs the new env, no image rebuild).
4. Delete the old ZIM once the new one serves.

## Install / remove the tool

```sh
docker cp deploy/. open-webui:/tmp/deploy/
docker exec -e PYTHONPATH=/app/backend:/tmp/deploy/native_assistant -w /app/backend open-webui \
  python /tmp/deploy/encyclopedia/manage_encyclopedia.py activate    # or deactivate
```

`activate` is idempotent: it creates or updates the public tool, binds it as a
required tool on the main model and recomposes the system prompt from
`native_assistant/system.txt` plus every bound companion tool's `instructions.txt`.
Later code or prompt edits are pushed with `native_assistant/manage.py refresh`.

## Tests

```sh
python3 -m unittest deploy/encyclopedia/tests/test_workspace_tool.py
```
