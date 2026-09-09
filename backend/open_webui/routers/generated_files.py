"""Authenticated proxy: renderer credentials and file ownership never reach the model."""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from uuid import UUID

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from open_webui.utils.auth import get_verified_user

router = APIRouter()
MAX_DOWNLOAD = 10 * 1024 * 1024


def signed_headers(method, path, owner, body=b''):
    key = Path('/run/secrets/file_generation_key').read_bytes()
    timestamp = str(int(time.time()))
    canonical = '\n'.join((method, path, owner, timestamp, hashlib.sha256(body).hexdigest()))
    return {
        'X-File-Owner': owner,
        'X-File-Time': timestamp,
        'X-File-Signature': hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest(),
        'Content-Type': 'application/json',
    }


async def renderer_request(method, path, owner, payload=None):
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if payload is not None else b''
    if len(body) > 512 * 1024:
        raise HTTPException(413, 'File request too large')
    try:
        headers = signed_headers(method, path, owner, body)
        base = os.getenv('FILE_GENERATION_URL', 'http://file-generation:8081')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
            async with session.request(
                method, base + path, data=body or None, headers=headers, allow_redirects=False
            ) as response:
                if response.status != 200:
                    code = response.status if response.status in (404, 410, 413, 422, 429) else 503
                    raise HTTPException(
                        code, 'File generation unavailable' if code == 503 else 'File unavailable or request rejected'
                    )
                output = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    output.extend(chunk)
                    if len(output) > MAX_DOWNLOAD:
                        raise HTTPException(502, 'Generated file exceeds download limit')
                return bytes(output), {key.lower(): value for key, value in response.headers.items()}
    except (OSError, aiohttp.ClientError, TimeoutError):
        raise HTTPException(503, 'File generation service unavailable') from None


async def generate_file(payload, user):
    owner = (user or {}).get('id')
    if not owner:
        raise HTTPException(401, 'User identity required')
    content, _ = await renderer_request('POST', '/render', owner, payload)
    result = json.loads(content)
    identifier = str(UUID(result['id']))
    base_url = f'/api/v1/generated-files/{identifier}'
    return {
        **result,
        'url': base_url,
        'preview_url': f'/api/v1/generated-files/preview/{identifier}',
    }


def _file_response(content, headers, *, inline=False):
    disposition = headers.get('content-disposition', 'attachment')
    if inline:
        disposition = disposition.replace('attachment', 'inline', 1)
    return Response(
        content,
        media_type=headers.get('content-type', 'application/octet-stream'),
        headers={
            'Content-Disposition': disposition,
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@router.get('/{identifier}')
async def download_generated_file(identifier: UUID, user=Depends(get_verified_user)):
    content, headers = await renderer_request('GET', f'/files/{identifier}', user.id)
    return _file_response(content, headers)


@router.get('/preview/{identifier}')
async def preview_generated_file(identifier: UUID, user=Depends(get_verified_user)):
    """Serve a generated artifact inline for the authenticated owner's preview viewer."""
    content, headers = await renderer_request('GET', f'/files/{identifier}', user.id)
    return _file_response(content, headers, inline=True)
