# A/B twin of lexuz_pipeline.py: identical proxy, but targets the v7
# RAG service (:4041) backed by the fine-tuned embedder + v7 collections.
# Lets the same kazus be asked of prod and v7 from the OpenWebUI model
# dropdown. Prod pipeline and prod RAG service are untouched.
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import hashlib
import hmac
import os
import json
import logging
import time
import requests

logger = logging.getLogger(__name__)


def _sanitize(value) -> str:
    """Strip and drop separator/control chars before signing (parity P1).

    The canonical string is "|"-joined, so a field containing "|" would make
    the encoding ambiguous and let a caller re-partition a valid signature
    into a higher-privilege identity. mcp-server rejects such fields outright;
    we remove them here so legitimate users with odd emails still work.
    Mirror of sanitize_field() in legal-rag/llamaindex/auth_signing.py.
    """
    return "".join(
        ch for ch in str(value or "").strip() if ch != "|" and ch.isprintable()
    )


def _chat_id(payload) -> str:
    """Resolve the chat id, which OpenWebUI nests under `metadata`.

    Newer OpenWebUI builds send {"metadata": {"chat_id": ..., "message_id": ...}}
    rather than a top-level `chat_id`; the top-level lookup silently yielded ""
    and broke the feedback->turn join (parity P2). Check both, metadata first.
    """
    meta = payload.get("metadata")
    if isinstance(meta, dict) and meta.get("chat_id"):
        return str(meta["chat_id"])
    return str(payload.get("chat_id") or "")


def _identity_headers(user_info, chat_id) -> dict:
    """HMAC-signed identity headers (parity P1).

    mcp-server verifies these with the shared MCP_AUTH_SECRET; without the
    secret we still send the plain X-User-Id (rate-limit contract, scaling
    P04). Canonical string MUST stay in sync with
    legal-rag/llamaindex/auth_signing.py: "v1|id|email|role|chat|ts".
    Self-contained copy in each pipeline file — this container can't import
    the legal-rag repo.
    """
    headers = {}
    if not (isinstance(user_info, dict) and user_info.get("id")):
        return headers
    uid = _sanitize(user_info["id"])[:128]
    email = _sanitize(user_info.get("email"))[:128]
    role = _sanitize(user_info.get("role"))[:64]
    cid = _sanitize(chat_id)[:128]
    if not uid:
        return headers
    headers["X-User-Id"] = uid
    if email:
        headers["X-User-Email"] = email
    if role:
        headers["X-User-Role"] = role
    if cid:
        headers["X-Chat-Id"] = cid
    secret = os.getenv("MCP_AUTH_SECRET", "").strip()
    if secret:
        ts = str(int(time.time()))
        msg = "|".join(("v1", uid, email, role, cid, ts))
        headers["X-Auth-Ts"] = ts
        headers["X-Auth-Sig"] = hmac.new(
            secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
    return headers


class Pipeline:
    """LexUz RAG pipe with structured research-timeline events.

    Translates named SSE frames from crawler-lexuz (`event: message`,
    `event: status`) into open-webui Pipelines events. See
    docs/lexuz-status-events.md in the open-webui repo for the
    event contract.
    """

    class Valves(BaseModel):
        LEX_UZ_RAG_URL: str = ""
        REQUEST_TIMEOUT: int = 600

    def __init__(self):
        self.name = "LexUz v7 (FT embedder)"
        self.valves = self.Valves(
            **{
                "LEX_UZ_RAG_URL": os.getenv(
                    "LEX_UZ_V7_RAG_URL",
                    "http://host.docker.internal:4041/lex_uz/stream",
                ).strip(),
                "REQUEST_TIMEOUT": int(os.getenv("REQUEST_TIMEOUT", "600")),
            }
        )
        self.session = requests.Session()

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        self.session.close()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        LEX_UZ_RAG_URL = self.valves.LEX_UZ_RAG_URL
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

        payload = body.copy()
        # OpenWebUI injects body["user"] = {id, name, email, role} for
        # pipeline models (routers/openai.py). Forward it as signed identity
        # headers (parity P1): id for rate limiting (P04), email/role for
        # authz, chat_id for Q&A joins (P2). The raw objects are still
        # stripped from the payload below.
        headers.update(_identity_headers(payload.get("user"), _chat_id(payload)))
        for field in ("user", "chat_id", "title"):
            payload.pop(field, None)

        try:
            r = self.session.post(
                url=LEX_UZ_RAG_URL,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            r.raise_for_status()

            def gen():
                try:
                    yield from _parse_and_forward(r)
                except requests.exceptions.ChunkedEncodingError:
                    logger.error("Upstream response ended prematurely")
                    yield "Error: Upstream response ended prematurely"
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed during streaming: {e}")
                    yield f"Error: Request failed during streaming - {e}"
                except Exception as e:
                    logger.exception(f"Unexpected error during streaming: {e}")
                    yield f"Error: Unexpected error during streaming - {e}"
                finally:
                    r.close()

            return gen()

        except requests.exceptions.Timeout:
            return f"Error: Request timed out after {self.valves.REQUEST_TIMEOUT}s"
        except requests.exceptions.RequestException as e:
            return f"Error: Request failed - {e}"
        except Exception as e:
            return f"Error: Unexpected error - {e}"


def _parse_and_forward(response):
    """Iterate an SSE response and yield content strings or event dicts.

    SSE frames are delimited by blank lines. Each frame may contain:
      event: <name>
      data: <line 1>
      data: <line 2>

    For multi-line `data` fields the concatenated lines are joined with \n,
    per the SSE spec. We forward `event: message` (and bare frames) as content,
    and `event: status` as parsed-JSON events.
    """
    event_name = None
    data_lines: List[str] = []

    for raw_line in response.iter_lines(decode_unicode=True):
        # iter_lines yields None on keepalive bytes; treat any falsy line as a
        # frame delimiter only if we actually accumulated something.
        if raw_line is None:
            continue
        line = raw_line.rstrip("\r")

        if line == "":
            # End of a frame. Emit and reset.
            if data_lines or event_name:
                yield from _emit_frame(event_name, "\n".join(data_lines))
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            # SSE comment — ignored.
            continue

        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            # Trim a single optional leading space after the colon.
            chunk = line[len("data:"):]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            data_lines.append(chunk)
        # All other field names (id:, retry:, etc.) are not used.

    # Flush a trailing frame if the stream ends without a blank line.
    if data_lines or event_name:
        yield from _emit_frame(event_name, "\n".join(data_lines))


def _emit_frame(event_name, data_str):
    """Yield the right shape based on event name."""
    if event_name == "status":
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("status frame had invalid JSON; dropping: %r", data_str[:200])
            return
        yield {"event": {"type": "status", "data": payload}}
        return

    # Drop SSE terminator frames (OpenAI-style stream end marker).
    if event_name == "done" or data_str.strip() == "[DONE]":
        return

    # Default branch: treat as content. Covers `event: message`, no event name,
    # and any unknown event we want to be forgiving about.
    if data_str:
        yield data_str
