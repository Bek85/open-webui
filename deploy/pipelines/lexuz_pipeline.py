from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)


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
        self.name = "LexUz"
        self.valves = self.Valves(
            **{
                "LEX_UZ_RAG_URL": os.getenv(
                    "LEX_UZ_RAG_URL",
                    "http://host.docker.internal:4040/lex_uz/stream",
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
        # pipeline models (routers/openai.py). Forward the stable account id
        # so mcp-server can rate-limit per user (scaling P04); the rest of the
        # user object (email etc.) is still stripped below.
        user_info = payload.get("user")
        if isinstance(user_info, dict) and user_info.get("id"):
            headers["X-User-Id"] = str(user_info["id"])[:128]
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
