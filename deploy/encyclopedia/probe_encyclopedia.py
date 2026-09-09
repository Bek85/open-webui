"""Live routing probe: do general-knowledge questions reach search_encyclopedia through the real chat?

Run inside WebUI: PYTHONPATH=/app/backend:/tmp/deploy/native_assistant python probe_encyclopedia.py
Uses temporary chats (never persisted). Prints tool calls, timing and a hit rate.
"""

import json
import sys
import threading
import time
import uuid

import requests
import socketio
from probe import auth_headers

MODEL = 'router_pipeline'
CASES = [
    ("Amir Temur kim bo'lgan?", True),
    ("Samarqand shahri haqida qisqacha ma'lumot ber", True),
    ('Fotosintez nima?', True),
    ('Orol dengizi nega quriyapti?', True),
    ('Алишер Навоий қачон туғилган?', True),
    ('Кто такой Юрий Гагарин?', True),
    ('Что такое инфляция?', True),
    ('Toshkent metrosi qachon ochilgan?', True),
    ('Salom, yaxshimisiz?', False),
    ('Ushbu matnni ruschaga tarjima qil: bugun ob-havo yaxshi', False),
]


def turn(question):  # noqa: C901 - socket handler nesting
    headers = auth_headers()
    client = socketio.Client()
    finished = threading.Event()
    mid = str(uuid.uuid4())
    calls, started = [], time.time()
    first_text = None
    wiki_sources = 0

    @client.on('events')
    def receive(event):  # noqa: C901 - one handler per event type
        nonlocal first_text
        if event.get('message_id') != mid:
            return
        data = event.get('data', {})
        payload = data.get('data', {})
        if data.get('type') == 'chat:completion':
            for item in payload.get('output') or []:
                if item.get('type') == 'function_call' and item.get('status') == 'completed':
                    args = json.loads(item.get('arguments') or '{}')
                    entry = (item.get('name'), args.get('query'), args.get('language'))
                    if entry not in calls:
                        calls.append(entry)
                if item.get('type') == 'message' and first_text is None:
                    if any(part.get('text') for part in item.get('content', [])):
                        first_text = time.time() - started
            if payload.get('done') or payload.get('error'):
                finished.set()
        elif data.get('type') in ('source', 'citation'):
            nonlocal wiki_sources
            if '/wiki/' in json.dumps(payload, ensure_ascii=False):
                wiki_sources += 1
        elif data.get('type') == 'chat:error':
            finished.set()

    client.connect(
        'http://127.0.0.1:8080',
        socketio_path='ws/socket.io',
        auth={'token': headers['Authorization'].removeprefix('Bearer ')},
        transports=['websocket'],
    )
    sid = client.get_sid()
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': question}],
        'stream': True,
        'params': {'function_calling': 'native'},
        'session_id': sid,
        'chat_id': 'temporary:' + sid,
        'id': mid,
        'files': [],
    }
    response = requests.post(
        'http://127.0.0.1:8080/api/chat/completions', json=payload, headers=headers, timeout=(20, 600)
    )
    assert response.status_code == 200, response.text[:300]
    finished.wait(600)
    client.disconnect()
    return calls, time.time() - started, first_text, wiki_sources


if __name__ == '__main__':
    hits = 0
    for question, expected in CASES:
        calls, total, first, wiki_sources = turn(question)
        # A server-side lookup shows up as encyclopedia source cards; a model-initiated one as a call.
        used = wiki_sources > 0 or any(name == 'search_encyclopedia' for name, _, _ in calls)
        ok = used == expected
        hits += ok
        print(
            f'{"OK  " if ok else "MISS"} used={"yes" if used else "no ":<3} sources={wiki_sources} '
            f'first_text={first if first is None else round(first, 1)}s total={total:.0f}s '
            f'calls={[(n, (q or "")[:40], lang) for n, q, lang in calls]} <= {question[:50]}',
            flush=True,
        )
    print(f'{hits}/{len(CASES)} routed as expected')
    sys.exit(0 if hits >= 8 else 1)
