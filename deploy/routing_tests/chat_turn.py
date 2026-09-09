"""One chat turn through the real Open WebUI API, summarised for routing checks.

Uses a temporary chat (never persisted) and the admin session used by the other
probes. Runs inside the WebUI container with deploy/native_assistant on PYTHONPATH.
"""

import json
import threading
import time
import uuid

import requests
import socketio
from probe import auth_headers

LEGAL_STATUSES = {'Researching legal sources…', 'Routing to LexUz pipeline…', 'Routing to Prosecutor pipeline…'}


class TurnResult:
    def __init__(self):
        self.calls = []  # (tool name, arguments dict)
        self.legal_stream = False  # legal fast path (specialist relayed, no tool call)
        self.wiki_sources = 0
        self.first_text = None
        self.total = 0.0
        self.error = None

    def used(self, tool: str | None) -> bool:
        """Whether the turn used the given tool by any mechanism (call, fast path, server-side lookup)."""
        if tool is None:
            return not self.calls and not self.legal_stream and self.wiki_sources == 0
        if tool in ('research_uzbek_law', 'research_prosecutor_orders'):
            return self.legal_stream or any(name == tool for name, _ in self.calls)
        if tool == 'search_encyclopedia':
            return self.wiki_sources > 0 or any(name == tool for name, _ in self.calls)
        if tool == 'create_document':
            return any(name in ('create_document', 'create_spreadsheet') for name, _ in self.calls)
        return any(name == tool for name, _ in self.calls)


def turn(messages: list, model: str = 'router_pipeline', timeout: int = 600) -> TurnResult:  # noqa: C901
    headers = auth_headers()
    client = socketio.Client()
    finished = threading.Event()
    mid = str(uuid.uuid4())
    result, started = TurnResult(), time.time()

    @client.on('events')
    def receive(event):  # noqa: C901 - one branch per event type
        if event.get('message_id') != mid:
            return
        data = event.get('data', {})
        payload = data.get('data', {})
        kind = data.get('type')
        if kind == 'status':
            if payload.get('description') in LEGAL_STATUSES:
                result.legal_stream = True
        elif kind in ('source', 'citation'):
            if '/wiki/' in json.dumps(payload, ensure_ascii=False):
                result.wiki_sources += 1
        elif kind == 'chat:completion':
            for item in payload.get('output') or []:
                if item.get('type') == 'function_call' and item.get('status') == 'completed':
                    try:
                        args = json.loads(item.get('arguments') or '{}')
                    except json.JSONDecodeError:
                        args = {}
                    entry = (item.get('name'), args)
                    if entry not in result.calls:
                        result.calls.append(entry)
                if item.get('type') == 'message' and result.first_text is None:
                    if any(part.get('text') for part in item.get('content', [])):
                        result.first_text = time.time() - started
            if payload.get('error'):
                result.error = str(payload['error'])[:200]
            if payload.get('done') or payload.get('error'):
                finished.set()
        elif kind == 'chat:error':
            result.error = str(payload)[:200]
            finished.set()

    client.connect(
        'http://127.0.0.1:8080',
        socketio_path='ws/socket.io',
        auth={'token': headers['Authorization'].removeprefix('Bearer ')},
        transports=['websocket'],
    )
    sid = client.get_sid()
    body = {
        'model': model,
        'messages': messages,
        'stream': True,
        'params': {'function_calling': 'native'},
        'session_id': sid,
        'chat_id': 'temporary:' + sid,
        'id': mid,
        'files': [],
    }
    try:
        response = requests.post(
            'http://127.0.0.1:8080/api/chat/completions', json=body, headers=headers, timeout=(20, timeout)
        )
        if response.status_code != 200:
            result.error = f'HTTP {response.status_code}'
            return result
        finished.wait(timeout)
    finally:
        client.disconnect()
    result.total = time.time() - started
    return result
