"""Deterministic legal routing for the unified ProkuraturaAI chat.

Native tool choice is a sampling coin flip on implicit legal questions (measured
2026-09-09: 5/8 hits at any temperature). For legal-only turns (no attachments)
this module classifies the question with a temperature-0 call and streams the
specialist service directly as the assistant answer, exactly like the legacy
router pipeline. Document-plus-law turns take the same path since 2026-09-11:
the uploaded text travels with the question as ``attachments`` and the
specialist plans its own searches, instead of the model issuing one research
call per issue (three sequential specialist runs, 11 minutes, on a 6-page file).
"""

import asyncio
import json
import logging
import os
import uuid

import aiohttp
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.document_context import FAST_PATH_MAX_CHARS, fast_path_documents
from open_webui.utils.legal_specialist_stream import identity_headers, relay_frames, sse_frames
from open_webui.utils.misc import get_content_from_message, get_last_user_message_item
from starlette.responses import JSONResponse, StreamingResponse

log = logging.getLogger(__name__)

RESEARCH_TOOL = 'research_uzbek_law'
CORPUS_BY_ROUTE = {'lexuz': 'lex_uz', 'prosecutor': 'prosecutor'}
# Native research calls that can be relayed as the answer instead of re-synthesized.
CORPUS_BY_TOOL = {'research_uzbek_law': 'lex_uz', 'research_prosecutor_orders': 'prosecutor'}
RELAY_TOOL_RESULT = 'The specialist answer was streamed to the user as the reply to this call.'
PREVIOUS_QUESTION_CHARS = 300
FILE_TOOLS = ('create_document', 'create_spreadsheet')
CALC_TOOLS = ('base_calculation_value', 'count_deadline')
# Routes where the model must call one of a small tool set on the first request.
FORCED_TOOLS_BY_ROUTE = {'file': FILE_TOOLS, 'calc': CALC_TOOLS}
MAX_HISTORY_MESSAGES = 12
MAX_MESSAGE_CHARS = 12000
CLASSIFY_TIMEOUT_SECONDS = 20
MODEL_ONLY_FEATURES = ('web_search', 'image_generation', 'code_interpreter')
# Prepended to the classifier input on document turns: the one-word classifier never
# sees attachments, and the same words route differently with a file behind them.
ATTACHED_DOCUMENT_PREFIX = '[Hujjat biriktirilgan] '

# Same tuned prompt as deploy/pipelines/router_pipeline.py (the legacy router).
CLASSIFY_SYSTEM = """Sen O'zbekiston huquqiy tizimi uchun so'rovlarni yo'naltiruvchi sistemasan.

Foydalanuvchi so'rovini o'qi va qaysi backend qayta ishlashi kerakligini aniqla:

Agar matnda "Oldingi savol:" va "Hozirgi so'rov:" bo'lsa, suhbat davom etmoqda:
  • hozirgi so'rov oldingi savolning davomi bo'lsa ("qayta qidir", "boshqacha so'zlar bilan",
    "batafsilroq", "yana", "shu haqida", "topilishi kerak", "to'liq ko'rsat", "boshqa
    moddalarni ham") → OLDINGI savolning yo'nalishini tanla
  • hozirgi so'rov mustaqil yangi mavzu bo'lsa → faqat hozirgi so'rov bo'yicha yo'naltir
  • "rahmat", "tushunarli", salomlashish kabi javoblar → general

Agar so'rov "[Hujjat biriktirilgan]" bilan boshlansa, foydalanuvchi hujjat yuklagan:
  • savolga hujjat matnining O'ZIDAN javob berish mumkin bo'lsa → general: mazmuni,
    bayoni, tarjimasi, jadvali; hujjatdagi shartlar, muddatlar, summalar, tomonlar,
    to'lov tartibi; "shartnomada/hujjatda nima yozilgan", "qaysi hollarda ... to'laydi /
    javob beradi" (hujjat shartlari bo'yicha) — qonun so'ralmagan
  • so'rovda QONUN, kodeks, qonunchilik, qonuniy javobgarlik, jazo, huquqiy chora
    yoki hujjatning qonunga muvofiqligi so'ralgan bo'lsa → lexuz

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

calc — aniq hisob-kitob so'rovlari (qonun mazmuni emas, faqat son yoki sana kerak):
  • Bazaviy hisoblash miqdori (BHM, БРВ) qiymati — hozir yoki ma'lum sanada
  • Summani BHM ga o'tkazish ("5 mln so'm necha BHM?", "50 BHM necha so'm?")
  • Muddat hisoblash: sanadan boshlab N kun / ish kuni / oy qachon tugaydi,
    oxirgi kun bayramga to'g'ri kelsa, ish kunlari soni
  Eslatma: "qaysi modda", "qanday jazo", "qaysi kategoriya", "qonunga ko'ra
  muddat necha kun" kabi huquqiy baho yoki norma kerak bo'lsa — lexuz.

general — yuqoridagilarning hech biriga tegishli bo'lmasa:
  • Salomlashish, muloqot, matn yozish yoki tarjima qilish iltimoslari
  • Yuklangan hujjat bilan ishlash (bayon, tarjima, jadval, hujjat matnidagi savollar)
  • Yordamchining o'zi haqidagi savollar ("sen kimsan?", "nimalar qila olasan?", "qanday yordam berasan?")

Faqat bitta so'z yoz: lexuz YOKI prosecutor YOKI wiki YOKI file YOKI calc YOKI general"""


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
    if 'calc' in text:
        return 'calc'
    return 'general'


def is_fast_path_candidate(metadata: dict, model: dict, tool_names) -> bool:
    """UI chat, research tool bound, no knowledge base or toggled features: safe to bypass the model.

    Attached files do not disqualify the turn here; ``plan_legal_fast_path`` reads them
    and keeps the model in charge when they cannot travel with the question.
    """
    meta = (model.get('info') or {}).get('meta') or {}
    features = metadata.get('features') or {}
    return bool(
        metadata.get('session_id')
        and not metadata.get('direct')
        and RESEARCH_TOOL in (tool_names or ())
        and meta.get('legalFastPath', True)
        and not meta.get('knowledge')
        and not any(features.get(name) for name in MODEL_ONLY_FEATURES)
    )


def classifier_text(question: str, has_documents: bool, previous: str | None = None) -> str:
    """What the route classifier reads: the question, with the previous question when the chat continues
    (a bare "search again with other words" carries no legal signal on its own), flagged when a document
    is attached."""
    text = question
    if previous:
        text = f"Oldingi savol: {previous[:PREVIOUS_QUESTION_CHARS]}\nHozirgi so'rov: {question}"
    return (ATTACHED_DOCUMENT_PREFIX + text) if has_documents else text


def previous_user_question(messages: list) -> str | None:
    """Text of the user turn before the last one, or None on the first turn."""
    users = [m for m in messages if m.get('role') == 'user']
    if len(users) < 2:
        return None
    text = get_content_from_message(users[-2])
    return text.strip() if isinstance(text, str) and text.strip() else None


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


def force_route_tools(form_data: dict, tool_names, route: str) -> bool:
    """Restrict the turn to the route's tools (FORCED_TOOLS_BY_ROUTE) and require one to be called.

    Free tool choice drops roughly one export in seven at the serving temperature
    (measured 2026-09-09, and independent of wording), so the model's discretion is
    removed here just as it is for the legal and encyclopedia routes. Only this first
    request is forced: the tool-call follow-up in process_chat_response drops
    `tool_choice`, otherwise the model would be made to call a tool forever.
    """
    wanted = FORCED_TOOLS_BY_ROUTE.get(route, ())
    available = {name for name in wanted if name in (tool_names or ())}
    specs = [spec for spec in (form_data.get('tools') or []) if (spec.get('function') or {}).get('name') in available]
    if not specs:
        log.warning('%s route: none of %s bound to this model; using native tools', route, wanted)
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
    """Route the turn: a specialist plan (has `corpus`), an encyclopedia plan (route `wiki`), or None.

    With files attached, only the legal routes are deterministic: the documents ride
    along as ``attachments`` when every file is readable and fits
    ``DOCUMENT_FAST_PATH_MAX_CHARS``; otherwise, and for every other route, the model
    keeps the turn and reads the file itself (utils/document_context.py).
    """
    if not is_fast_path_candidate(metadata, model, tool_names):
        return None
    question = plain_text_question(form_data.get('messages', []))
    if question is None:
        return None
    documents = None
    if metadata.get('files'):
        documents = await fast_path_documents(metadata, user, FAST_PATH_MAX_CHARS)
        if documents is None:
            return None
    base_model_id = (model.get('info') or {}).get('base_model_id') or form_data.get('model')
    previous = previous_user_question(form_data.get('messages', []))
    route = await classify_route(request, user, base_model_id, classifier_text(question, bool(documents), previous))
    corpus = CORPUS_BY_ROUTE.get(route)
    if corpus:
        return {
            'route': route,
            'corpus': corpus,
            'question': question,
            'messages': specialist_messages(form_data.get('messages', [])),
            'attachments': documents or [],
        }
    if documents:
        return None
    if route == 'wiki' or route in FORCED_TOOLS_BY_ROUTE:
        # Handled in process_chat_payload and the model still writes the answer:
        # 'wiki' gets a server-side lookup, 'file'/'calc' get a forced tool call.
        return {'route': route, 'question': question}
    return None


def legal_relay_plan(tool_calls: list, form_data: dict, metadata: dict, model: dict, tool_names) -> dict | None:
    """A fast-path plan for a lone native research call on a plain chat turn, else None.

    When the classifier hands a turn to the model and the model still calls a research
    tool, the tool path would wait for the specialist's whole answer and then have the
    model write a second one (measured 2026-09-11: first text after ~3 min versus 11-28 s
    relayed). Relaying applies only to a single research call without attachments; document
    turns and multi-tool turns keep the loop, because the model must combine the results.
    The model's rewritten query becomes the final user turn: it is usually sharper than a
    bare "search again", and the specialist still sees the conversation before it.
    """
    if len(tool_calls or []) != 1 or metadata.get('files'):
        return None
    if not is_fast_path_candidate(metadata, model, tool_names):
        return None
    call = tool_calls[0]
    function = call.get('function') or {}
    corpus = CORPUS_BY_TOOL.get(function.get('name'))
    if not corpus:
        return None
    try:
        query = (json.loads(function.get('arguments') or '{}') or {}).get('query')
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    if not isinstance(query, str) or not query.strip():
        return None
    history = specialist_messages(form_data.get('messages', []))
    if history and history[-1]['role'] == 'user':
        history = history[:-1]
    route = next(route for route, name in CORPUS_BY_ROUTE.items() if name == corpus)
    return {
        'route': route,
        'corpus': corpus,
        'question': query.strip(),
        'messages': [*history, {'role': 'user', 'content': query.strip()[:MAX_MESSAGE_CHARS]}],
        'attachments': [],
        'tool_call': call,
    }


def specialist_request_body(plan: dict) -> dict:
    """The stream request: history plus, on document turns, the attachments the specialist reads."""
    body = {'messages': plan['messages'], 'stream': True}
    if plan.get('attachments'):
        body['attachments'] = plan['attachments']
    return body


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
            f'{base_url}/{plan["corpus"]}/stream', json=specialist_request_body(plan), headers=headers
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

    log.info(
        'Legal fast path: request=%s corpus=%s attachments=%s streaming',
        request_id,
        plan['corpus'],
        len(plan.get('attachments') or []),
    )
    body = relay_frames(
        sse_frames(response.content), form_data.get('model', ''), plan['corpus'], plan['question'], close_upstream
    )
    streaming = StreamingResponse(body, media_type='text/event-stream')
    streaming.close_upstream = close_upstream
    return streaming
