"""Synthetic smoke tests; no real user chats/documents are read."""

import argparse
import base64
import datetime as dt
import json
import os
import threading
import uuid
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import requests
import socketio
from manage import CANARY_ID, TOOL_ID, api, database
from PIL import Image, ImageDraw


def auth_headers():
    from open_webui.utils.auth import create_token

    with database() as db:
        uid = db.execute("SELECT user_id FROM model WHERE id='ProkuraturaAI'").fetchone()[0]
    return {'Authorization': 'Bearer ' + create_token({'id': uid}, dt.timedelta(minutes=20))}


def chat(messages, model, files=None, label='chat', show_answer=True):
    headers = auth_headers()
    client = socketio.Client()
    finished = threading.Event()
    events, output, errors = [], [], []
    mid = str(uuid.uuid4())

    @client.on('events')
    def receive(event):
        nonlocal output
        if event.get('message_id') != mid:
            return  # Never inspect or retain events belonging to a real chat.
        data = event.get('data', {})
        events.append(data)
        payload = data.get('data', {})
        if data.get('type') == 'chat:completion':
            if payload.get('output'):
                output = payload['output']
            if payload.get('error'):
                errors.append(payload['error'])
            if payload.get('done') or payload.get('error'):
                finished.set()
        elif data.get('type') == 'chat:error':
            errors.append(payload)
            finished.set()

    client.connect(
        'http://127.0.0.1:8080',
        socketio_path='ws/socket.io',
        auth={'token': headers['Authorization'].removeprefix('Bearer ')},
        transports=['websocket'],
    )
    sid = client.get_sid()
    payload = {
        'model': model,
        'messages': messages,
        'stream': True,
        'tool_ids': [TOOL_ID],
        'params': {'function_calling': 'native', 'temperature': 0.1},
        'session_id': sid,
        'chat_id': 'temporary:' + sid,
        'id': mid,
        'files': files or [],
    }
    try:
        response = requests.post(
            'http://127.0.0.1:8080/api/chat/completions', json=payload, headers=headers, timeout=(20, 660)
        )
        if response.status_code != 200:
            raise RuntimeError(f'Chat HTTP {response.status_code}: {response.text[:400]}')
        assert finished.wait(660), 'Timed out waiting for UI completion event'
        assert not errors, errors
    finally:
        client.disconnect()
    Path('/tmp/native-assistant-' + label + '.json').write_text(json.dumps(events, ensure_ascii=False))
    content = '\n'.join(
        part.get('text', '')
        for item in output
        if item.get('type') == 'message'
        for part in item.get('content', [])
        if part.get('type') == 'output_text'
    )
    names = [item.get('name') for item in output if item.get('type') == 'function_call']
    source_count = sum(event.get('type') in ('source', 'citation') for event in events)
    print(
        label,
        'tools:',
        names,
        'source cards:',
        source_count,
        'answer:',
        content[-1100:] if show_answer else f'{len(content)} characters (not displayed)',
        flush=True,
    )
    assert content.strip(), 'No final answer returned'
    return content, names, output


def prosecutor(model):
    api('/api/models')
    _, names, output = chat(
        [
            {
                'role': 'user',
                'content': (
                    'Bosh prokurorning prokuratura organlarida ish yuritishni tashkil etishga oid '
                    'buyruqlarini ichki hujjatlar bazasidan qidiring. Manbalarga tayangan qisqa javob bering.'
                ),
            }
        ],
        model,
        label='prosecutor',
        show_answer=False,
    )
    assert 'research_prosecutor_orders' in names, 'Wrong research tool selected'
    for item in output:
        if item.get('type') == 'function_call_output':
            for part in item.get('output', []):
                result = json.loads(part.get('text', '{}'))
                assert 'error' not in result, result.get('error')
    print('PASS: authorized prosecutor research through the UI native loop', flush=True)


def pdf_fixture():
    text = (
        'BT /F1 14 Tf 60 760 Td (TEST CONTRACT - synthetic fixture) Tj 0 -30 Td '
        '(Verification code: GAUDI-4821.) Tj 0 -30 Td (Annual paid leave: 12 calendar days.) Tj ET'
    )
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(text)} >>\nstream\n{text}\nendstream'.encode(),
    ]
    result, offsets = b'%PDF-1.4\n', [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f'{idx} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(result)
    result += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def workflow(model):
    assert any(m['id'] == model for m in api('/api/models')['data']), 'Test model not available'
    messages = [{'role': 'user', 'content': 'Salom! Qisqacha salom bering.'}]
    answer, names, _ = chat(messages, model, label='greeting')
    assert not names, 'Greeting unexpectedly called tools'
    messages += [
        {'role': 'assistant', 'content': answer},
        {
            'role': 'user',
            'content': (
                'O‘zbekiston Mehnat kodeksida yillik asosiy eng kam mehnat ta’tili necha kalendar kun? '
                'LexUz manbasini tekshiring va qisqa javob bering.'
            ),
        },
    ]
    answer, names, _ = chat(messages, model, label='law')
    assert 'research_uzbek_law' in names and 'lex.uz/' in answer, 'Legal research/citation missing'
    messages += [{'role': 'assistant', 'content': answer}]
    response = requests.post(
        'http://127.0.0.1:8080/api/v1/files/?process_in_background=false',
        headers=auth_headers(),
        files={'file': ('native-smoke.pdf', pdf_fixture(), 'application/pdf')},
        timeout=180,
    )
    response.raise_for_status()
    uploaded = response.json()
    fid = uploaded['id']
    print('Synthetic PDF uploaded:', fid, 'status:', uploaded.get('data', {}).get('status'), flush=True)
    try:
        file = {'id': fid, 'name': 'native-smoke.pdf', 'type': 'file', 'file': uploaded}
        messages += [
            {
                'role': 'user',
                'content': (
                    f'<attached_files><file id="{fid}" name="native-smoke.pdf"/></attached_files>\n'
                    'Faqat PDFni o‘qing: undagi tekshiruv kodi va ta’til kunlari sonini yozing. '
                    'Hozir qonunni tekshirish kerak emas.'
                ),
            }
        ]
        answer, names, _ = chat(messages, model, files=[file], label='pdf-after-law')
        assert 'GAUDI-4821' in answer and '12' in answer, 'PDF facts not read correctly'
        assert not any(name.startswith('research_') for name in names), (
            'PDF-only request incorrectly sent to legal research'
        )
        messages += [
            {'role': 'assistant', 'content': answer},
            {
                'role': 'user',
                'content': (
                    'Endi ushbu PDFdagi 12 kunlik yillik ta’til bandi qonundagi eng kam ta’tilga mos keladimi? '
                    'Amaldagi Mehnat kodeksini LexUz orqali qayta tekshirib, hujjat bilan solishtiring. '
                    'Qisqa javob bering.'
                ),
            },
        ]
        answer, names, _ = chat(messages, model, files=[file], label='pdf-plus-law')
        assert 'research_uzbek_law' in names and 'lex.uz/' in answer, 'Combined research/citation missing'
        print('PASS: greeting, legal research, PDF after law, and document-plus-law workflow', flush=True)
    finally:
        response = requests.delete('http://127.0.0.1:8080/api/v1/files/' + fid, headers=auth_headers(), timeout=20)
        response.raise_for_status()
        print('Synthetic PDF removed; no real chat or file was modified.', flush=True)


def direct(payload):
    config = api('/openai/config')
    request = Request(
        config['OPENAI_API_BASE_URLS'][0].rstrip('/') + '/chat/completions',
        data=json.dumps({'model': 'ProkuraturaAI', 'stream': False, 'max_tokens': 2048, **payload}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config['OPENAI_API_KEYS'][0]},
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.load(response)['choices'][0]['message']
    except HTTPError as error:
        print('Direct model error:', error.code, error.read().decode()[:600])
        raise


def capabilities():
    result = direct(
        {
            'messages': [
                {
                    'role': 'user',
                    'content': 'Call the echo tool with text native-ready. Do not answer without calling it.',
                }
            ],
            'tools': [
                {
                    'type': 'function',
                    'function': {
                        'name': 'echo',
                        'description': 'Echo test text',
                        'parameters': {
                            'type': 'object',
                            'properties': {'text': {'type': 'string'}},
                            'required': ['text'],
                        },
                    },
                }
            ],
            'tool_choice': 'auto',
        }
    )
    assert result.get('tool_calls'), 'No structured native tool call returned'
    assert result['tool_calls'][0]['function']['name'] == 'echo'
    print('PASS: direct model returns structured native tool calls', flush=True)
    picture = Image.new('RGB', (336, 336), 'white')
    ImageDraw.Draw(picture).rectangle((65, 65, 270, 270), fill='red')
    buffer = BytesIO()
    picture.save(buffer, format='PNG')
    result = direct(
        {
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': 'What color is the large shape in this image? Answer with one English color word.',
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
                            },
                        },
                    ],
                }
            ]
        }
    )
    assert 'red' in result.get('content', '').lower(), result.get('content')
    print('PASS: direct model identifies the synthetic red image', flush=True)


def access_boundary():
    from legal_research import identity_headers

    secret = os.environ['MCP_AUTH_SECRET']
    headers = identity_headers(
        {'id': 'native-smoke-unprivileged', 'role': 'user', 'email': 'native-smoke@example.invalid'},
        'native-smoke-auth',
        secret,
    )
    headers['X-Eval-Run'] = '1'
    response = requests.post(
        os.environ['RAG_BASE_URL'].rstrip('/') + '/prosecutor/stream',
        headers=headers,
        json={'messages': [{'role': 'user', 'content': 'Authorization probe'}], 'stream': True},
        timeout=20,
    )
    assert response.status_code == 403, f'Expected a signed-but-unauthorized 403, got {response.status_code}'
    print('PASS: real prosecutor service rejects a signed unprivileged identity (403)', flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capabilities', 'workflow', 'access', 'prosecutor'])
    parser.add_argument('--model', default=CANARY_ID)
    args = parser.parse_args()
    if args.action == 'capabilities':
        capabilities()
    elif args.action == 'access':
        access_boundary()
    elif args.action == 'prosecutor':
        prosecutor(args.model)
    else:
        workflow(args.model)
