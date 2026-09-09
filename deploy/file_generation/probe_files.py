"""Synthetic native-chat and owner-download checks. Never reads real user chats/files."""

import argparse
import json
import os
import re
from io import BytesIO
from zipfile import ZipFile

import requests
from manage import database
from probe import auth_headers, chat


def check(model):
    os.umask(0o077)
    with database() as db:
        other = db.execute("SELECT id FROM user WHERE role='user' LIMIT 1").fetchone()
    assert other, 'A non-admin account is required for the read-only isolation check'
    queries = {
        'docx': (
            'Word (.docx) fayl yarating. Sarlavha: Fayl yaratish sinovi. '
            'Matn: Ўзбекистон, Ғ, Қ, Ҳ, Ў. O‘zbekiston. Русский текст. '
            'Ikki ustunli jadval ham bo‘lsin: Nomi, Soni; Sinov, 12. Bu faqat texnik sinov.'
        ),
        'pdf': (
            'PDF fayl yarating. Sarlavha: PDF sinovi. '
            'Matn: Ўзбекистон, Ғ, Қ, Ҳ, Ў. O‘zbekiston. Русский текст. '
            'Faqat shu matndan foydalaning, boshqa ma’lumot kerak emas.'
        ),
        'xlsx': (
            'Excel (.xlsx) fayl yarating. Jadval nomi: Sinov. Ustunlar: Nomi, Soni. '
            'Qatorlar: Birinchi, 12; Ikkinchi, 7. Boshqa ma’lumot qo‘shmang.'
        ),
    }
    for extension, query in queries.items():
        answer, names, output = chat(
            [{'role': 'user', 'content': query}], model, label='file-' + extension, show_answer=False
        )
        expected = 'create_spreadsheet' if extension == 'xlsx' else 'create_document'
        assert expected in names, f'{extension}: missing native tool call'
        assert not any(name.startswith('research_') for name in names), 'Simple file creation triggered legal research'
        artifacts = []
        for item in output:
            if item.get('type') == 'function_call_output':
                for part in item.get('output', []):
                    value = json.loads(part.get('text', '{}'))
                    if 'url' in value:
                        artifacts.append(value)
                    assert not value.get('error'), value.get('error')
        assert artifacts, 'No generated artifact returned'
        for artifact in artifacts:
            url = artifact['url']
            assert re.fullmatch(r'/api/v1/generated-files/[a-f0-9-]{36}', url), 'Unexpected download URL'
            assert url in answer, 'Assistant omitted the actual download link'
            endpoint = 'http://127.0.0.1:8080' + url
            response = requests.get(endpoint, headers=auth_headers(), timeout=30)
            assert response.status_code == 200, response.status_code
            assert 'attachment' in response.headers.get('Content-Disposition', '')
            assert response.headers.get('Cache-Control') == 'private, no-store'
            assert requests.get(endpoint, timeout=30).status_code == 401
            assert requests.get(endpoint, headers=auth_headers(other[0]), timeout=30).status_code == 404
            if extension == 'pdf':
                assert response.content.startswith(b'%PDF-')
                assert b'/ToUnicode' in response.content
            else:
                with ZipFile(BytesIO(response.content)) as archive:
                    part = 'word/document.xml' if extension == 'docx' else 'xl/worksheets/sheet1.xml'
                    assert part in archive.namelist()
            print(f'PASS {extension}: native call, real download, anonymous/other-user denied', flush=True)
    print('PASS: all three formats through the native chat flow', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='prokuratura_files_canary')
    check(parser.parse_args().model)
