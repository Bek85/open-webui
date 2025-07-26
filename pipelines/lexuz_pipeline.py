from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import os
import requests


class Pipeline:
    class Valves(BaseModel):
        LEX_UZ_RAG_URL: str = ""
        pass

    def __init__(self):
        # self.id = "openai_pipeline"
        self.name = "LexUz"
        self.valves = self.Valves(
            **{
                "LEX_UZ_RAG_URL": os.getenv("LEX_UZ_RAG_URL", "http://host.docker.internal:4040/stream")
            }
        )
        self.session = requests.Session()
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        self.session.close()
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        print(messages)
        print(user_message)

        LEX_UZ_RAG_URL = self.valves.LEX_UZ_RAG_URL

        headers = {}
        headers["Content-Type"] = "application/json"

        payload = body

        if "user" in payload:
            del payload["user"]
        if "chat_id" in payload:
            del payload["chat_id"]
        if "title" in payload:
            del payload["title"]

        print(payload)

        try:
            r = self.session.post(
                url=LEX_UZ_RAG_URL,
                json=payload,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()

            return r.iter_content(chunk_size=1024)
        except Exception as e:
            return f"Error: {e}"
