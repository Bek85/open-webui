from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

# Classifier prompt in Uzbek — model handles Uzbek legal queries better than English labels.
# NOTE (2026-07-04): the `prosecutor` backend is an internal RAG over "Bosh prokuror buyruqlari"
# (Prosecutor General's orders / internal prosecutor-office directives) — NOT a criminal-law
# advice service. The old prompt described it as "jinoyat ishlari, tergov, ayblov", which mis-routed
# citizen criminal questions (e.g. "moshinada odam urib kettim, nima bo'ladi?") there instead of
# to lexuz. Prosecutor is now restricted to internal-directive lookups; all public legal/criminal
# questions — even first-person — go to lexuz.
CLASSIFY_SYSTEM = """Sen O'zbekiston huquqiy tizimi uchun so'rovlarni yo'naltiruvchi sistemasan.

Foydalanuvchi so'rovini o'qi va qaysi backend qayta ishlashi kerakligini aniqla:

lexuz — O'zbekiston qonunchiligi bo'yicha har qanday huquqiy savol (fuqarolar uchun):
  • Kodekslar, qonunlar, moddalar (JK, FK, MK, JPK, Mehnat kodeksi va boshqalar)
  • Biror harakat, jinoyat yoki huquqbuzarlik uchun javobgarlik, jazo yoki oqibat —
    HATTO so'rov birinchi shaxsda bo'lsa ham ("men ... qildim, endi nima bo'ladi?")
  • Huquqiy normalar, qoidalar, nizomlarni qidirish yoki tushuntirish
  • Fuqaroning huquqiy holati, huquq va majburiyatlari
  • Lex.uz saytidagi hujjatlar

prosecutor — FAQAT prokuraturaning ichki idoraviy hujjatlari:
  • Bosh prokurorning buyruqlari, ko'rsatmalari, farmoyishlari
  • Prokuratura ichki reglamentlari, tartib-qoidalari, direktivalari
  • Prokuratura xodimlariga mo'ljallangan idoraviy hujjatlar
  Eslatma: fuqaroning jinoyat, huquqbuzarlik yoki qonun mazmuni haqidagi savoli
  BU YERGA EMAS — u lexuz ga tegishli.

general — yuqoridagilarning hech biriga tegishli bo'lmasa:
  • Umumiy savollar, salomlashish, muloqot
  • Texnik, ilmiy, madaniy va boshqa mavzular
  • Huquq yoki prokuratura bilan bog'liq bo'lmagan har qanday so'rov

Faqat bitta so'z yoz: lexuz YOKI prosecutor YOKI general"""


class Pipeline:
    """ProkuraturaAI smart router — classifies query intent, streams from the right backend."""

    class Valves(BaseModel):
        LEX_UZ_URL: str = ""
        PROSECUTOR_URL: str = ""
        CLASSIFIER_BASE_URL: str = ""
        CLASSIFIER_KEY: str = ""
        CLASSIFIER_MODEL: str = "ProkuraturaAI"
        REQUEST_TIMEOUT: int = 600

    def __init__(self):
        self.name = "ProkuraturaAI"
        self.valves = self.Valves(
            **{
                "LEX_UZ_URL": os.getenv(
                    "LEX_UZ_RAG_URL", "http://172.18.35.123:4040/lex_uz/stream"
                ).strip(),
                "PROSECUTOR_URL": os.getenv(
                    "PROSECUTOR_RAG_URL", "http://172.18.35.123:4040/prosecutor/stream"
                ).strip(),
                "CLASSIFIER_BASE_URL": os.getenv(
                    "CLASSIFIER_BASE_URL",
                    os.getenv("OPENAI_API_BASE_URL", "http://172.17.0.1:8000/v1"),
                ).strip(),
                "CLASSIFIER_KEY": os.getenv(
                    "CLASSIFIER_KEY", os.getenv("OPENAI_API_KEY", "")
                ).strip(),
                "CLASSIFIER_MODEL": os.getenv("CLASSIFIER_MODEL", "ProkuraturaAI").strip(),
                "REQUEST_TIMEOUT": int(os.getenv("REQUEST_TIMEOUT", "600")),
            }
        )
        self.session = requests.Session()

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        self.session.close()

    def _classify(self, user_message: str) -> str:
        """Classify query as 'lexuz' or 'prosecutor'. Falls back to 'lexuz' on any error."""
        try:
            resp = self.session.post(
                url=f"{self.valves.CLASSIFIER_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.valves.CLASSIFIER_KEY}",
                },
                json={
                    "model": self.valves.CLASSIFIER_MODEL,
                    "messages": [
                        {"role": "system", "content": CLASSIFY_SYSTEM},
                        {"role": "user", "content": user_message[:800]},
                    ],
                    "max_tokens": 10,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip().lower()
            if "prosecutor" in text:
                route = "prosecutor"
            elif "general" in text:
                route = "general"
            else:
                route = "lexuz"
            logger.info(f"Router: classified as {route!r} (model said: {text!r})")
            return route
        except Exception as e:
            logger.warning(f"Router: classification failed, defaulting to lexuz: {e}")
            return "lexuz"

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        route = self._classify(user_message)

        if route == "general":
            return self._forward_to_model(messages, body)

        target_url = (
            self.valves.PROSECUTOR_URL if route == "prosecutor" else self.valves.LEX_UZ_URL
        )
        route_label = "Prosecutor" if route == "prosecutor" else "LexUz"

        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        payload = body.copy()
        for field in ("user", "chat_id", "title"):
            payload.pop(field, None)

        try:
            r = self.session.post(
                url=target_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            r.raise_for_status()

            def gen():
                yield {
                    "event": {
                        "type": "status",
                        "data": {
                            "action": "reasoning",
                            "description": f"Routing to {route_label} pipeline…",
                            "done": True,
                        },
                    }
                }
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

    def _forward_to_model(self, messages: List[dict], body: dict) -> Generator:
        """Stream directly from the model endpoint for general (non-legal) queries."""
        payload = {
            "model": self.valves.CLASSIFIER_MODEL,
            "messages": messages,
            "stream": True,
        }
        for key in ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty"):
            if key in body:
                payload[key] = body[key]

        try:
            r = self.session.post(
                url=f"{self.valves.CLASSIFIER_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.valves.CLASSIFIER_KEY}",
                    "Accept": "text/event-stream",
                },
                json=payload,
                stream=True,
                timeout=self.valves.REQUEST_TIMEOUT,
            )
            r.raise_for_status()

            def gen():
                try:
                    for raw_line in r.iter_lines(decode_unicode=True):
                        if not raw_line or raw_line.startswith(":"):
                            continue
                        line = raw_line.rstrip("\r")
                        if line.startswith("data:"):
                            chunk = line[5:].lstrip(" ")
                            if chunk == "[DONE]":
                                break
                            try:
                                delta = json.loads(chunk)
                                content = delta["choices"][0]["delta"].get("content")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
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
    """Iterate SSE response and yield content strings or event dicts.

    SSE frames are delimited by blank lines. Each frame may contain:
      event: <name>
      data: <line>

    Forwards event:message and bare frames as content strings;
    event:status as parsed-JSON event dicts for the research timeline UI.
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
            continue  # SSE comment

        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            chunk = line[len("data:"):]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            data_lines.append(chunk)

    # Flush final frame if stream ended without trailing blank line
    if data_lines or event_name:
        yield from _emit_frame(event_name, "\n".join(data_lines))


def _emit_frame(event_name, data_str):
    """Yield the correct shape based on SSE event name."""
    if event_name == "status":
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("status frame had invalid JSON; dropping: %r", data_str[:200])
            return
        yield {"event": {"type": "status", "data": payload}}
        return

    # Drop OpenAI-style stream terminator
    if event_name == "done" or data_str.strip() == "[DONE]":
        return

    # Default: treat as content (covers event:message, no event, unknown events)
    if data_str:
        yield data_str
