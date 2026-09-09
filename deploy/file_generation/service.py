"""Private, signed renderer API. Artifacts are owner-scoped and expire automatically."""

import asyncio
import hashlib
import hmac
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from renderer import MIME, GenerateRequest, filename_for, register_fonts, render

DATA = Path(os.getenv('FILE_GENERATION_DATA', '/data'))
KEY_PATH = Path(os.getenv('FILE_GENERATION_KEY_PATH', '/run/secrets/file_generation_key'))
RETENTION = 30 * 86400
MAX_BODY = 512 * 1024
QUOTA_BYTES = 2 * 1024 * 1024 * 1024
LOCK = threading.Lock()
log = logging.getLogger('file_generation')


@contextmanager
def database():
    db = sqlite3.connect(DATA / 'artifacts.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    if len(KEY_PATH.read_bytes()) < 32:
        raise RuntimeError('A dedicated signing key is required')
    register_fonts()
    with database() as db:
        db.execute(
            'CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, owner TEXT NOT NULL, '
            'format TEXT NOT NULL, filename TEXT NOT NULL, size INTEGER NOT NULL, expires_at INTEGER NOT NULL)'
        )
        db.execute('CREATE INDEX IF NOT EXISTS artifacts_owner ON artifacts(owner)')


def artifact_path(identifier, fmt):
    if str(uuid.UUID(identifier)) != identifier or fmt not in MIME:
        raise ValueError('Invalid artifact reference')
    return DATA / (identifier + '.' + fmt)


def cleanup():
    # This volume contains generated artifacts only, never uploads or user chats.
    with LOCK, database() as db:
        now = int(time.time())
        for row in db.execute('SELECT id, format FROM artifacts WHERE expires_at <= ?', (now,)).fetchall():
            artifact_path(row['id'], row['format']).unlink(missing_ok=True)
            db.execute('DELETE FROM artifacts WHERE id=?', (row['id'],))
        known = {row['id'] for row in db.execute('SELECT id FROM artifacts')}
        for path in DATA.iterdir():
            if (
                re.fullmatch(r'[0-9a-f-]{36}\.(pdf|docx|xlsx)', path.name)
                and path.stem not in known
                and path.stat().st_mtime < now - 3600
            ):
                path.unlink()


async def cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(cleanup)
        except Exception as exc:
            log.warning('Artifact cleanup failed: %s', type(exc).__name__)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    initialize()
    app.state.slots = asyncio.Semaphore(2)
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def authenticate(request, body=b''):
    owner = request.headers.get('X-File-Owner', '')
    timestamp = request.headers.get('X-File-Time', '')
    signature = request.headers.get('X-File-Signature', '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', owner):
        raise HTTPException(401, 'Invalid identity')
    try:
        if abs(time.time() - int(timestamp)) > 60:
            raise ValueError()
    except ValueError:
        raise HTTPException(401, 'Expired request') from None
    canonical = '\n'.join((request.method, request.url.path, owner, timestamp, hashlib.sha256(body).hexdigest()))
    expected = hmac.new(KEY_PATH.read_bytes(), canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'Invalid signature')
    return owner


def save_artifact(spec, owner):
    output = render(spec)
    identifier, expires = str(uuid.uuid4()), int(time.time()) + RETENTION
    filename = filename_for(spec)
    path = artifact_path(identifier, spec.format)
    with LOCK, database() as db:
        count = db.execute('SELECT COUNT(*) FROM artifacts WHERE owner=?', (owner,)).fetchone()[0]
        total = db.execute('SELECT COALESCE(SUM(size),0) FROM artifacts').fetchone()[0]
        if count >= 100 or total + len(output) > QUOTA_BYTES:
            raise HTTPException(429, 'Generated file quota reached')
        try:
            with path.open('xb') as target:
                target.write(output)
            db.execute(
                'INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                (identifier, owner, spec.format, filename, len(output), expires),
            )
            db.commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return {
        'id': identifier,
        'filename': filename,
        'size': len(output),
        'content_type': MIME[spec.format],
        'expires_at': expires,
    }


@app.get('/health')
async def health():
    return {'status': True}


@app.post('/render')
async def create(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, 'Document request too large')
    owner = authenticate(request, bytes(body))
    try:
        spec = GenerateRequest.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, 'Invalid document structure or size limits exceeded') from None
    if request.app.state.slots.locked():
        raise HTTPException(429, 'Renderer busy; try again shortly')
    async with request.app.state.slots:
        try:
            return await asyncio.to_thread(save_artifact, spec, owner)
        except HTTPException:
            raise
        except ValueError:
            raise HTTPException(422, 'Document cannot be rendered within supported limits') from None
        except Exception as exc:
            log.warning('Rendering failed: %s', type(exc).__name__)
            raise HTTPException(500, 'File generation failed') from None


@app.get('/files/{identifier}')
async def download(identifier: uuid.UUID, request: Request):
    owner = authenticate(request)
    with database() as db:
        row = db.execute('SELECT * FROM artifacts WHERE id=? AND owner=?', (str(identifier), owner)).fetchone()
    if row is None:
        raise HTTPException(404, 'File not found')
    if row['expires_at'] <= time.time():
        raise HTTPException(410, 'File expired')
    return FileResponse(
        artifact_path(row['id'], row['format']),
        filename=row['filename'],
        media_type=MIME[row['format']],
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'},
    )
