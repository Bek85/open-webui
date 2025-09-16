from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import requests
import logging

logger = logging.getLogger(__name__)


class Pipeline:
    class Valves(BaseModel):
        PROSECUTOR_RAG_URL: str = ""
        REQUEST_TIMEOUT: int = 600

    def __init__(self):
        self.name = "Prosecutor"
        self.valves = self.Valves(
            **{
                "PROSECUTOR_RAG_URL": os.getenv(
                    "PROSECUTOR_RAG_URL",
                    "http://host.docker.internal:4040/prosecutor/stream"
                ).strip(),
                "REQUEST_TIMEOUT": int(os.getenv("REQUEST_TIMEOUT", "600")),
            }
        )
        self.session = requests.Session()

    async def on_startup(self):
        # Called when the server is started.
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        # Called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        self.session.close()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        """
        Custom pipeline logic: sends the request to the Prosecutor RAG service
        and streams the response back to the client.
        """
        print(f"pipe:{__name__}")
        print(messages)
        print(user_message)

        PROSECUTOR_RAG_URL = self.valves.PROSECUTOR_RAG_URL

        headers = {"Content-Type": "application/json"}

        # Create a copy of body to avoid mutating the original
        payload = body.copy()

        # Remove unnecessary fields
        fields_to_remove = ["user", "chat_id", "title"]
        for field in fields_to_remove:
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

            # Generator to properly decode streaming text response
            def stream_response():
                try:
                    for chunk in r.iter_content(
                        chunk_size=1024, decode_unicode=True
                    ):
                        if chunk:
                            if isinstance(chunk, bytes):
                                yield chunk.decode("utf-8", errors="ignore")
                            else:
                                yield chunk
                except requests.exceptions.ChunkedEncodingError:
                    logger.error("Upstream response ended prematurely (Prosecutor RAG)")
                    yield "Error: Upstream response ended prematurely"
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed during streaming: {e}")
                    yield f"Error: Request failed during streaming - {str(e)}"
                except Exception as e:
                    logger.error(f"Unexpected error during streaming: {e}")
                    yield f"Error: Unexpected error during streaming - {str(e)}"
                finally:
                    r.close()

            return stream_response()

        except requests.exceptions.Timeout:
            return f"Error: Request timed out after {self.valves.REQUEST_TIMEOUT} seconds"
        except requests.exceptions.RequestException as e:
            return f"Error: Request failed - {str(e)}"
        except Exception as e:
            return f"Error: Unexpected error - {str(e)}"
