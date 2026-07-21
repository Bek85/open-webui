from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)


class Pipeline:
    """Prosecutor RAG pipe with structured research-timeline events.

    Translates named SSE frames from the prosecutor backend (`event: message`,
    `event: status`) into open-webui Pipelines events. See
    docs/lexuz-status-events.md in the open-webui repo for the event contract
    (shared with LexUz).
    """

    class Valves(BaseModel):
        PROSECUTOR_RAG_URL: str = ""
        REQUEST_TIMEOUT: int = 600

    def __init__(self):
        self.name = "Prosecutor"
        self.valves = self.Valves(
            **{
                "PROSECUTOR_RAG_URL": os.getenv(
                    "PROSECUTOR_RAG_URL",
                    "http://host.docker.internal:4040/prosecutor/stream",
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
        PROSECUTOR_RAG_URL = self.valves.PROSECUTOR_RAG_URL
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

        payload = body.copy()
        # Forward the stable OpenWebUI account id for per-user rate limiting
        # (scaling P04) — same contract as lexuz_pipeline.py.
        user_info = payload.get("user")
        if isinstance(user_info, dict) and user_info.get("id"):
            headers["X-User-Id"] = str(user_info["id"])[:128]
        for field in ("user", "chat_id", "title"):
            payload.pop(field, None)

        try:
            r = self.session.post(
                url=PROSECUTOR_RAG_URL,
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
        if raw_line is None:
            continue
        line = raw_line.rstrip("\r")

        if line == "":
            if data_lines or event_name:
                yield from _emit_frame(event_name, "\n".join(data_lines))
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            chunk = line[len("data:"):]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            data_lines.append(chunk)

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
