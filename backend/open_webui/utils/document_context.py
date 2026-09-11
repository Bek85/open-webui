"""Whole-document context for uploaded files that fit the model's window.

A document turn delivers only top-k chunks (embedded locally with MiniLM, weak
for Uzbek) unless the file item carries `context: 'full'`, which the UI exposes
as a manual toggle. The chat model serves 262K tokens, and measured 2026-09-11 a
139 000-character judgment answered faster in full than through retrieval, so
files within the cap are supplied whole by default. The model is told which case
applies so it can be honest about coverage (see deploy/native_assistant/system.txt).
"""

import logging
import os

from open_webui.models.files import Files
from open_webui.utils.access_control.files import has_access_to_file
from open_webui.utils.misc import add_or_update_system_message

log = logging.getLogger(__name__)

# About a third of the 262 144-token window; Uzbek Cyrillic tokenizes at ~2.5 chars/token.
MAX_FULL_CONTEXT_CHARS = int(os.getenv('DOCUMENT_FULL_CONTEXT_MAX_CHARS', '450000'))


def attached_file_items(metadata: dict) -> list:
    """Uploaded file items that have not been given an explicit context mode by the user."""
    return [
        item
        for item in (metadata.get('files') or [])
        if isinstance(item, dict)
        and item.get('type', 'file') == 'file'
        and item.get('id')
        and not str(item['id']).startswith(('http://', 'https://', 'data:'))
        and not item.get('context')
    ]


async def readable_length(item: dict, user) -> int | None:
    """Characters of extracted text the user may read for this item; None when not readable."""
    record = await Files.get_file_by_id(item['id'])
    if not record:
        return None
    allowed = user.role == 'admin' or record.user_id == user.id or await has_access_to_file(item['id'], 'read', user)
    if not allowed:
        return None
    return len((record.data or {}).get('content') or '')


async def plan_document_context(metadata: dict, user, max_chars: int = MAX_FULL_CONTEXT_CHARS) -> dict | None:
    """Mark file items `context: 'full'` when their text fits; describe what was decided."""
    items = attached_file_items(metadata)
    if not items:
        return None
    files = []
    for item in items:
        length = await readable_length(item, user)
        if length:
            files.append({'item': item, 'name': item.get('name') or item['id'], 'chars': length})
    if not files:
        return None
    total = sum(entry['chars'] for entry in files)
    mode = 'full' if total <= max_chars else 'excerpts'
    if mode == 'full':
        for entry in files:
            entry['item']['context'] = 'full'
    return {'mode': mode, 'chars': total, 'files': [(entry['name'], entry['chars']) for entry in files]}


def system_note(plan: dict) -> str:
    names = ', '.join(f'{name} ({chars:,} characters)' for name, chars in plan['files'])
    if plan['mode'] == 'full':
        return f'Attached document(s) supplied IN FULL, one source per file: {names}. Treat each as the complete text.'
    return (
        f'Attached document(s) too large for whole-document reading ({plan["chars"]:,} characters): {names}. '
        'Only retrieved excerpts are supplied; say so and limit claims to them.'
    )


def status_text(plan: dict) -> str:
    if plan['mode'] == 'full':
        pages = max(1, round(plan['chars'] / 2500))
        return f'Butun hujjat o‘qilmoqda (~{pages} sahifa)'
    return 'Hujjat juda katta: faqat tegishli parchalar o‘qilmoqda'


async def apply_document_context(form_data: dict, metadata: dict, user, event_emitter=None) -> dict | None:
    """Decide full vs excerpts for this turn, tell the user (status) and the model (system note)."""
    plan = await plan_document_context(metadata, user)
    if not plan:
        return None
    form_data['messages'] = add_or_update_system_message(system_note(plan), form_data.get('messages', []), append=True)
    if event_emitter:
        await event_emitter({'type': 'status', 'data': {'description': status_text(plan), 'done': True}})
    log.info('Document context: mode=%s chars=%s files=%s', plan['mode'], plan['chars'], len(plan['files']))
    return plan
