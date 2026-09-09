"""Transport and relay for the legal specialist service (crawler-lexuz mcp-server).

Signed identity headers, SSE frame parsing and the translation of specialist
frames into the chat stream the middleware already understands. Used by
legal_fast_path.py; keeps no routing logic.
"""

import hashlib
import hmac
import json
import logging
import re
import time

import aiohttp
from open_webui.utils.misc import openai_chat_chunk_message_template

log = logging.getLogger(__name__)


def identity_headers(user: dict, chat_id, secret: str) -> dict:
    """Same v1 signed identity contract as the pipelines and the research tool."""

    def clean(value, limit):
        return ''.join(c for c in str(value or '').strip() if c != '|' and c.isprintable())[:limit]

    uid = clean(user.get('id'), 128)
    if not uid or not secret:
        raise ValueError('Signed user identity is required for legal research.')
    email, role, chat = clean(user.get('email'), 128), clean(user.get('role'), 64), clean(chat_id, 128)
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), '|'.join(('v1', uid, email, role, chat, timestamp)).encode(), hashlib.sha256
    ).hexdigest()
    return {
        'X-User-Id': uid,
        'X-User-Email': email,
        'X-User-Role': role,
        'X-Chat-Id': chat,
        'X-Auth-Ts': timestamp,
        'X-Auth-Sig': signature,
    }


async def sse_frames(content):
    """Parse SSE frames (multi-line data, unclosed final frame) from an aiohttp stream."""
    event, data = 'message', []
    async for raw in content:
        line = raw.decode('utf-8', 'replace').rstrip('\r\n')
        if not line:
            if data:
                yield event, '\n'.join(data)
            event, data = 'message', []
        elif line.startswith('event:'):
            event = line[6:].strip()
        elif line.startswith('data:'):
            data.append(line[5:].removeprefix(' '))
    if data:
        yield event, '\n'.join(data)


def bibliography_sources(answer: str) -> list:
    """Native source cards for links the specialist actually cited in its report."""
    sources, seen = [], set()
    for title, url in re.findall(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)', answer):
        if url in seen:
            continue
        seen.add(url)
        sources.append(
            {
                'source': {'id': url, 'name': title[:512], 'type': 'web'},
                'document': [title[:512]],
                'metadata': [{'source': url, 'url': url, 'name': title[:512]}],
            }
        )
    return sources[:64]


def failure_text(question: str) -> str:
    cyrillic = bool(re.search(r'[Ѐ-ӿ]', question or ''))
    if cyrillic:
        return (
            'Ҳуқуқий манбалар билан алоқа узилди, тасдиқланган жавоб йўқ. '
            'Илтимос, бироз вақтдан сўнг қайта уриниб кўринг.'
        )
    return (
        "Huquqiy manbalar bilan aloqa uzildi, tasdiqlangan javob yo'q. "
        "Iltimos, biroz vaqtdan so'ng qayta urinib ko'ring."
    )


# Protocol, failure and cleanup branches stay in one scope on purpose (same as the tool).
def relay_frames(frames, model_id: str, corpus: str, question: str, finalize=None):  # noqa: C901
    """Translate specialist SSE frames into the chat stream the middleware already understands.

    Status frames are forwarded untouched, exactly like the legacy pipeline (the specialist's
    `summary` row is the timeline header the UI collapses to); message frames become content
    deltas, and cited links become native source cards at the end. Upstream cleanup runs
    exactly once, also when the consumer closes the stream early.
    """

    def line(obj) -> bytes:
        return f'data: {json.dumps(obj, ensure_ascii=False)}\n\n'.encode()

    def status(description, started_at, done, error=False):
        data = {'action': 'reasoning', 'description': description, 'started_at': started_at, 'done': done}
        if done:
            data['ended_at'] = int(time.time() * 1000)
            data['error'] = error
        return line({'event': {'type': 'status', 'data': data}})

    async def generate():
        research_started = int(time.time() * 1000)
        state = {'parts': [], 'completed': False, 'pending': {}, 'connected': False}
        try:
            # Placeholder until the specialist reports its own steps.
            yield status('Researching legal sources…', research_started, False)
            try:
                async for chunk in _relay_events(frames, model_id, state, research_started, status, line):
                    yield chunk
            except (TimeoutError, aiohttp.ClientError, UnicodeError) as exc:
                log.warning(
                    'Legal fast path: stream failed corpus=%s exception=%s chars=%s',
                    corpus,
                    type(exc).__name__,
                    sum(map(len, state['parts'])),
                )
            answer = ''.join(state['parts'])
            completed = state['completed'] and bool(answer.strip()) and not answer.startswith('Error:')
            if not completed:
                # Partial text stays visible, but is never presented as a verified answer.
                notice = ('\n\n' if answer.strip() else '') + failure_text(question)
                yield line(openai_chat_chunk_message_template(model_id, notice))
            ended = int(time.time() * 1000)
            for step in state['pending'].values():  # specialist steps left open by a broken stream
                yield line(
                    {'event': {'type': 'status', 'data': {**step, 'done': True, 'ended_at': ended, 'error': True}}}
                )
            if not state['connected']:
                yield status('Researching legal sources…', research_started, True, error=not completed)
            if completed:
                for source in bibliography_sources(answer):
                    yield line({'event': {'type': 'source', 'data': source}})
            else:
                yield status('Legal research failed', ended, True, error=True)
            yield line(openai_chat_chunk_message_template(model_id))
            yield b'data: [DONE]\n\n'
        finally:
            if finalize:
                await finalize()

    return generate()


async def _relay_events(frames, model_id, state, research_started, status, line):  # noqa: C901
    """Forward one specialist frame at a time; tracks open steps so failures can close them."""
    async for event, data in frames:
        if event == 'done' or data.strip() == '[DONE]':
            state['completed'] = True
            return
        if event == 'error':
            return
        if event not in ('status', 'message') or not data:
            continue
        if not state['connected']:
            # First specialist frame: the placeholder step is over.
            state['connected'] = True
            yield status('Researching legal sources…', research_started, True)
        if event == 'status':
            try:
                detail = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(detail, dict):
                continue
            key = (detail.get('action'), detail.get('started_at'))
            if detail.get('done') is False and not detail.get('ended_at'):
                state['pending'][key] = detail
            else:
                state['pending'].pop(key, None)
            yield line({'event': {'type': 'status', 'data': detail}})
        else:
            state['parts'].append(data)
            yield line(openai_chat_chunk_message_template(model_id, data))
