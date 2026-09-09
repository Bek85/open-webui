"""Deterministic legal routing for the unified ProkuraturaAI chat.

Native tool choice is a sampling coin flip on implicit legal questions (measured
2026-09-09: 5/8 hits at any temperature). For legal-only turns (no attachments)
this module classifies the question with a temperature-0 call and streams the
specialist service directly as the assistant answer, exactly like the legacy
router pipeline. Document-plus-law turns keep the native tool path.
"""

import asyncio
import json
import logging
import os
import uuid

import aiohttp
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.legal_specialist_stream import identity_headers, relay_frames, sse_frames
from open_webui.utils.misc import get_content_from_message, get_last_user_message_item
from starlette.responses import JSONResponse, StreamingResponse

log = logging.getLogger(__name__)

RESEARCH_TOOL = 'research_uzbek_law'
CORPUS_BY_ROUTE = {'lexuz': 'lex_uz', 'prosecutor': 'prosecutor'}
FILE_TOOLS = ('create_document', 'create_spreadsheet')
MAX_HISTORY_MESSAGES = 12
MAX_MESSAGE_CHARS = 12000
CLASSIFY_TIMEOUT_SECONDS = 20
MODEL_ONLY_FEATURES = ('web_search', 'image_generation', 'code_interpreter')

# Same tuned prompt as deploy/pipelines/router_pipeline.py (the legacy router).
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

wiki — huquqqa aloqasi bo'lmagan umumiy bilim (ensiklopedik) savollari:
  • Shaxslar, joylar, mamlakatlar, tarixiy voqealar, fan, texnika, tabiat
  • Atamalar va tushunchalarning umumiy ta'rifi ("... nima?", "... kim?", "qachon ...")
  Eslatma: qonun, kodeks, javobgarlik, huquq va prokuraturaga oid savollar BU YERGA EMAS.

file — suhbatdagi mavjud javobni yoki ma'lumotni yuklab olinadigan faylga aylantirish:
  • "PDF qilib ber", "Word faylga chiqarib ber", "Excel jadval qilib ber"
  • "yuklab olishim uchun tayyorla", "shu ma'lumotlarni faylga saqlab ber"
  Eslatma: FAQAT suhbatda ALLAQACHON mavjud matnni faylga o'tkazish.
  Agar avval qonunchilikni o'rganish kerak bo'lsa — lexuz; prokuratura
  hujjatlarini o'rganib yangi hisobot tuzish kerak bo'lsa — prosecutor.

general — yuqoridagilarning hech biriga tegishli bo'lmasa:
  • Salomlashish, muloqot, matn yozish yoki tarjima qilish iltimoslari
  • Yuklangan hujjat bilan ishlash
  • Yordamchining o'zi haqidagi savollar ("sen kimsan?", "nimalar qila olasan?", "qanday yordam berasan?")

Faqat bitta so'z yoz: lexuz YOKI prosecutor YOKI wiki YOKI file YOKI general"""


def parse_route(text) -> str:
    """Map the classifier's one-word answer to a route; anything unclear is 'general'."""
    text = str(text or '').strip().lower()
    if 'prosecutor' in text:
        return 'prosecutor'
    if 'lexuz' in text or 'lex_uz' in text or 'lex.uz' in text:
        return 'lexuz'
    if 'wiki' in text:
        return 'wiki'
    if 'file' in text:
        return 'file'
    return 'general'


def is_fast_path_candidate(metadata: dict, model: dict, tool_names) -> bool:
    """UI chat, research tool bound, no attachments, knowledge or toggled features: safe to bypass the model."""
    meta = (model.get('info') or {}).get('meta') or {}
    features = metadata.get('features') or {}
    return bool(
        metadata.get('session_id')
        and not metadata.get('direct')
        and RESEARCH_TOOL in (tool_names or ())
        and meta.get('legalFastPath', True)
        and not metadata.get('files')
        and not meta.get('knowledge')
        and not any(features.get(name) for name in MODEL_ONLY_FEATURES)
    )


def plain_text_question(messages: list) -> str | None:
    """The last user message as text, or None when it carries images or other non-text parts."""
    message = get_last_user_message_item(messages)
    if not message:
        return None
    content = message.get('content')
    if isinstance(content, list) and any((part or {}).get('type') != 'text' for part in content):
        return None
    text = get_content_from_message(message)
    return text if isinstance(text, str) and text.strip() else None


def specialist_messages(messages: list) -> list:
    """Text-only recent history; the specialist builds its own context from it."""
    history = []
    for message in messages:
        if message.get('role') not in ('user', 'assistant'):
            continue
        text = get_content_from_message(message)
        if isinstance(text, str) and text.strip():
            history.append({'role': message['role'], 'content': text.strip()[:MAX_MESSAGE_CHARS]})
    return history[-MAX_HISTORY_MESSAGES:]


def force_file_tools(form_data: dict, tool_names) -> bool:
    """Restrict the turn to the file tools and require one of them to be called.

    Free tool choice drops roughly one export in seven at the serving temperature
    (measured 2026-09-09, and independent of wording), so the model's discretion is
    removed here just as it is for the legal and encyclopedia routes. Only this first
    request is forced: the tool-call follow-up in process_chat_response drops
    `tool_choice`, otherwise the model would be made to call a tool forever.
    """
    available = {name for name in FILE_TOOLS if name in (tool_names or ())}
    specs = [spec for spec in (form_data.get('tools') or []) if (spec.get('function') or {}).get('name') in available]
    if not specs:
        log.warning('File route: no file tool bound to this model; using native tools')
        return False
    form_data['tools'] = specs
    form_data['tool_choice'] = 'required'
    return True


async def classify_route(request, user, model_id: str, text: str) -> str:
    """Temperature-0 one-word classification on the base model; 'general' on any failure."""
    payload = {
        'model': model_id,
        'stream': False,
        'temperature': 0,
        'max_tokens': 10,
        'messages': [{'role': 'system', 'content': CLASSIFY_SYSTEM}, {'role': 'user', 'content': text[:800]}],
    }
    try:
        result = await asyncio.wait_for(
            generate_chat_completion(request, payload, user, bypass_filter=True, bypass_system_prompt=True),
            CLASSIFY_TIMEOUT_SECONDS,
        )
        if isinstance(result, JSONResponse):
            result = json.loads(result.body)
        route = parse_route(result['choices'][0]['message']['content'])
        log.info('Legal router: route=%s', route)
        return route
    except Exception as exc:  # noqa: BLE001 - routing must never break the chat
        log.warning('Legal router: classification failed (%s); using native tools', type(exc).__name__)
        return 'general'


async def plan_legal_fast_path(request, form_data: dict, user, metadata: dict, model: dict, tool_names) -> dict | None:
    """Route the turn: a specialist plan (has `corpus`), an encyclopedia plan (route `wiki`), or None."""
    if not is_fast_path_candidate(metadata, model, tool_names):
        return None
    question = plain_text_question(form_data.get('messages', []))
    if question is None:
        return None
    base_model_id = (model.get('info') or {}).get('base_model_id') or form_data.get('model')
    route = await classify_route(request, user, base_model_id, question)
    corpus = CORPUS_BY_ROUTE.get(route)
    if corpus:
        return {
            'route': route,
            'corpus': corpus,
            'question': question,
            'messages': specialist_messages(form_data.get('messages', [])),
        }
    if route in ('wiki', 'file'):
        # Both are handled in process_chat_payload and the model still writes the answer:
        # 'wiki' gets a server-side lookup, 'file' gets a forced file-tool call.
        return {'route': route, 'question': question}
    return None


async def start_legal_fast_path(form_data: dict, user, metadata: dict, plan: dict):
    """Open the specialist stream; return a StreamingResponse, or None to fall back to the model.

    The response carries `close_upstream` so the caller can release the connection if it
    fails before the body is ever iterated.
    """
    base_url = os.getenv('RAG_BASE_URL', 'http://host.docker.internal:4040').rstrip('/')
    try:
        timeout = int(os.getenv('LEGAL_FAST_PATH_TIMEOUT_SECONDS', '600'))
    except ValueError:
        timeout = 600
    try:
        headers = identity_headers(
            {'id': user.id, 'email': user.email, 'role': user.role},
            metadata.get('chat_id'),
            os.getenv('MCP_AUTH_SECRET', '').strip(),
        )
    except ValueError:
        log.warning('Legal fast path: signed identity unavailable; using native tools')
        return None
    request_id = uuid.uuid4().hex[:12]
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
    response = None
    try:
        response = await session.post(
            f'{base_url}/{plan["corpus"]}/stream', json={'messages': plan['messages'], 'stream': True}, headers=headers
        )
        usable = response.status < 400 and 'text/event-stream' in response.headers.get('Content-Type', '')
    except (TimeoutError, aiohttp.ClientError) as exc:
        log.warning('Legal fast path: request=%s connect failed %s; using native tools', request_id, type(exc).__name__)
        usable = False
    except BaseException:  # cancellation (stop button) or unexpected error: never leak the session
        await session.close()
        raise
    if not usable:
        if response is not None:
            log.warning(
                'Legal fast path: request=%s corpus=%s status=%s; using native tools',
                request_id,
                plan['corpus'],
                response.status,
            )
            response.release()
        await session.close()
        return None

    closed = False

    async def close_upstream():
        nonlocal closed
        if not closed:
            closed = True
            response.release()
            await session.close()

    log.info('Legal fast path: request=%s corpus=%s streaming', request_id, plan['corpus'])
    body = relay_frames(
        sse_frames(response.content), form_data.get('model', ''), plan['corpus'], plan['question'], close_upstream
    )
    streaming = StreamingResponse(body, media_type='text/event-stream')
    streaming.close_upstream = close_upstream
    return streaming
