"""Run inside open-webui: snapshot and provision the native assistant via local APIs."""

import argparse
import copy
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen

TOOL_ID = 'prokuratura_legal_research'
CANARY_ID = 'prokuratura_native_canary'
MAIN_ID = 'router_pipeline'
# 'user' + '*' means authenticated users. 'anyone' is an anonymous-sharing
# grant, which these model/tool APIs deliberately strip even for admins.
PUBLIC_READ = [{'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}]
ROOT = Path(__file__).resolve().parent


def database():
    return sqlite3.connect('file:/app/backend/data/webui.db?mode=ro', uri=True)


def api(path, payload=None, method=None):
    from open_webui.utils.auth import create_token

    with database() as db:
        row = db.execute("SELECT user_id FROM model WHERE id='ProkuraturaAI'").fetchone()
        uid = row[0]
        assert db.execute('SELECT role FROM user WHERE id=?', (uid,)).fetchone()[0] == 'admin'
    token = create_token({'id': uid}, dt.timedelta(minutes=10))
    req = Request(
        'http://127.0.0.1:8080' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method=method,
    )
    with urlopen(req, timeout=660) as response:
        return json.load(response)


def snapshot(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    os.umask(0o077)
    with database() as source, sqlite3.connect(destination / 'webui.db') as target:
        source.backup(target)
        assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for name, path in (
        ('models', '/api/v1/models/export'),
        ('tools', '/api/v1/tools/export'),
        ('openai', '/openai/config'),
        ('functions', '/api/v1/functions/export'),
    ):
        (destination / (name + '.json')).write_text(json.dumps(api(path), ensure_ascii=False, indent=2))
    backup_base_models(destination)
    print('Restore point created; SQLite integrity check passed:', destination)


def backup_base_models(destination):
    # /models/export omits base-model overrides in this Open WebUI version.
    with database() as db:
        ids = [row[0] for row in db.execute('SELECT id FROM model')]
    models = [api('/api/v1/models/model?id=' + mid) for mid in ids]
    path = destination / 'all-models.json'
    with path.open('x') as out:
        os.chmod(path, 0o600)
        json.dump(models, out, ensure_ascii=False, indent=2)
    print('Base-model overrides included:', len(models))


def native_model(mid, public=False):
    return {
        'id': mid,
        'base_model_id': 'ProkuraturaAI',
        'name': 'ProkuraturaAI' if mid == MAIN_ID else 'ProkuraturaAI — native canary',
        'is_active': True,
        'access_grants': PUBLIC_READ if public else [],
        'params': {'system': (ROOT / 'system.txt').read_text(), 'function_calling': 'native'},
        'meta': {
            'description': 'Unified assistant with documents, LexUz and Bosh prokuror buyruqlari.',
            'toolIds': [TOOL_ID],
            'requiredToolIds': [TOOL_ID],
            'capabilities': {
                'vision': False,
                'file_upload': True,
                'file_context': True,
                'builtin_tools': True,
                'citations': True,
                'status_updates': True,
                'web_search': False,
                'image_generation': False,
                'code_interpreter': False,
            },
            'builtinTools': {
                key: key in ('files', 'time')
                for key in (
                    'files',
                    'time',
                    'knowledge',
                    'web_search',
                    'image_generation',
                    'code_interpreter',
                    'memory',
                    'notes',
                    'channels',
                    'automations',
                    'calendar',
                    'skills',
                    'subagents',
                    'terminal',
                    'chats',
                    'tasks',
                    'notifications',
                )
            },
        },
    }


def tool_form(public=False):
    return {
        'id': TOOL_ID,
        'name': 'LexUz / Bosh prokuror buyruqlari',
        'content': (ROOT / 'legal_research.py').read_text(),
        'meta': {'description': 'Signed, permission-aware legal research for ProkuraturaAI.'},
        'access_grants': PUBLIC_READ if public else [],
    }


def stage(destination):
    assert (destination / 'all-models.json').is_file(), 'Complete restore point required'
    assert os.getenv('MCP_AUTH_SECRET', '').strip(), 'Signing secret missing'
    with database() as db:
        assert not db.execute('SELECT id FROM tool WHERE id=?', (TOOL_ID,)).fetchone(), (
            'Tool already exists; inspect before overwriting'
        )
        assert not db.execute('SELECT id FROM model WHERE id IN (?,?)', (CANARY_ID, MAIN_ID)).fetchone(), (
            'Migration model ID already exists'
        )
    api('/api/v1/tools/create', tool_form())
    base = next(m for m in json.loads((destination / 'all-models.json').read_text()) if m['id'] == 'ProkuraturaAI')
    base = {**base, 'is_active': True, 'access_grants': [], 'name': 'ProkuraturaAI — base (internal)'}
    api('/api/v1/models/model/update', base)
    api('/api/v1/models/create', native_model(CANARY_ID))
    print('Private native canary created; main assistant remains unchanged.')


def activate(destination):
    assert (destination / 'all-models.json').is_file(), 'Complete restore point required'
    config = api('/openai/config')
    saved = json.loads((destination / 'openai.json').read_text())
    assert config == saved, 'Provider settings changed since backup; inspect before activation'
    updated = copy.deepcopy(config)
    keys = config['OPENAI_API_KEYS']
    for idx, url in enumerate(config['OPENAI_API_BASE_URLS']):
        options = updated['OPENAI_API_CONFIGS'].setdefault(str(idx), {})
        if not options.get('enable', True):
            continue
        request = Request(url.rstrip('/') + '/models', headers={'Authorization': 'Bearer ' + keys[idx]})
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
        ids = [m['id'] for m in data['data']]
        if MAIN_ID in ids:
            # An upstream model wins over a same-ID workspace preset: remove only
            # the legacy router from discovery, retaining every specialist model.
            # Keep dynamic discovery and its pipeline metadata (signed-user
            # forwarding depends on it); do not replace with static model_ids.
            options['exclude_model_ids'] = list(dict.fromkeys([*options.get('exclude_model_ids', []), MAIN_ID]))
    with (destination / 'applied-openai.json').open('x') as out:
        os.chmod(out.name, 0o600)
        json.dump(updated, out)
    tool = api('/api/v1/tools/id/' + TOOL_ID + '/update', tool_form(public=True))
    model = api('/api/v1/models/create', native_model(MAIN_ID, public=True))
    for resource in (tool, model):
        assert any(
            grant['principal_type'] == 'user' and grant['principal_id'] == '*' and grant['permission'] == 'read'
            for grant in resource['access_grants']
        ), 'Authenticated-user grant was not retained by the API'
    api('/openai/config/update', updated)
    main = next(m for m in api('/api/models')['data'] if m['id'] == MAIN_ID)
    assert main.get('info', {}).get('base_model_id') == 'ProkuraturaAI', 'Native mapping not effective'
    assert not main.get('pipeline'), 'Legacy pipeline still active'
    print('Activated native assistant under the existing router_pipeline chat model ID.')


def rollback(destination):
    # Selective rollback preserves every chat and upload created since backup.
    current = api('/openai/config')
    saved = json.loads((destination / 'openai.json').read_text())
    applied_path = destination / 'applied-openai.json'
    applied = json.loads(applied_path.read_text()) if applied_path.exists() else saved
    assert current in (saved, applied), 'Provider settings changed; review before rollback'
    api('/openai/config/update', saved)
    with database() as db:
        mids = {r[0] for r in db.execute('SELECT id FROM model')}
        tids = {r[0] for r in db.execute('SELECT id FROM tool')}
    for mid in (MAIN_ID, CANARY_ID):
        if mid in mids:
            api('/api/v1/models/model/delete', {'id': mid})
    if TOOL_ID in tids:
        api('/api/v1/tools/id/' + TOOL_ID + '/delete', method='DELETE')
    base = next(m for m in json.loads((destination / 'all-models.json').read_text()) if m['id'] == 'ProkuraturaAI')
    api('/api/v1/models/model/update', base)
    print('Legacy routing restored. Chats, uploads and other model settings preserved.')


def inventory():
    print(
        'Available models:',
        [{key: m.get(key) for key in ('id', 'name', 'owned_by', 'pipe', 'urlIdx')} for m in api('/api/models')['data']],
    )
    for fn in api('/api/v1/functions/export'):
        print('Function:', {k: fn.get(k) for k in ('id', 'name', 'type', 'is_active', 'is_global')})
        for line in fn.get('content', '').splitlines():
            if any(word in line for word in ('router_pipeline', 'body[', 'model', 'class ', 'def ')):
                print(line[:200])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'action', choices=['snapshot', 'backup-base-models', 'inventory', 'stage', 'activate', 'rollback']
    )
    parser.add_argument('--restore-dir', type=Path)
    args = parser.parse_args()
    if args.action != 'inventory':
        assert args.restore_dir, '--restore-dir is required'
        {
            'snapshot': snapshot,
            'backup-base-models': backup_base_models,
            'stage': stage,
            'activate': activate,
            'rollback': rollback,
        }[args.action](args.restore_dir)
    else:
        inventory()
