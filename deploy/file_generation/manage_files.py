"""Private staging and selective activation. Run inside WebUI with native_assistant on PYTHONPATH."""

import argparse
import copy
import json
import os
from pathlib import Path

from manage import MAIN_ID, PUBLIC_READ, api

ROOT = Path(__file__).resolve().parent
TOOL_ID = 'prokuratura_file_generation'
CANARY_ID = 'prokuratura_files_canary'


def model_payload(model):
    return {k: model[k] for k in ('id', 'name', 'base_model_id', 'meta', 'params', 'is_active', 'access_grants')}


def augmented(model):
    result = copy.deepcopy(model_payload(model))
    for key in ('toolIds', 'requiredToolIds'):
        result['meta'][key] = list(dict.fromkeys([*(result['meta'].get(key) or []), TOOL_ID]))
    instructions = (ROOT / 'instructions.txt').read_text()
    system = result['params'].get('system', '')
    if instructions not in system:
        result['params']['system'] = system + '\n\n' + instructions
    return result


def tool_form(public=False):
    return {
        'id': TOOL_ID,
        'name': 'Word / PDF / Excel',
        'content': (ROOT / 'workspace_tool.py').read_text(),
        'meta': {'description': 'Private document generation; downloads expire after 30 days.'},
        'access_grants': PUBLIC_READ if public else [],
    }


def stage(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    main = api('/api/v1/models/model?id=' + MAIN_ID)
    tools = api('/api/v1/tools/')
    assert not any(t['id'] == TOOL_ID for t in tools), 'File tool already exists; do not overwrite'
    (destination / 'main-model.json').write_text(json.dumps(main, ensure_ascii=False))
    api('/api/v1/tools/create', tool_form())
    canary = augmented(main)
    canary.update(id=CANARY_ID, name='ProkuraturaAI — file creation test', access_grants=[])
    api('/api/v1/models/create', canary)
    print('Private file-generation canary created. Main model unchanged. Backup:', destination)


def activate(destination):
    main = api('/api/v1/models/model?id=' + MAIN_ID)
    saved = json.loads((destination / 'main-model.json').read_text())
    assert model_payload(main) == model_payload(saved), 'Main model changed after staging; inspect before activation'
    tool = api('/api/v1/tools/id/' + TOOL_ID + '/update', tool_form(public=True))
    assert any(all(g.get(k) == v for k, v in PUBLIC_READ[0].items()) for g in tool['access_grants'])
    result = api('/api/v1/models/model/update', augmented(main))
    assert TOOL_ID in result['meta']['requiredToolIds']
    (destination / 'activated-model.json').write_text(json.dumps(result, ensure_ascii=False))
    print('File creation enabled on the existing ProkuraturaAI model. Other model settings preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'activate'])
    parser.add_argument('--restore-dir', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    {'stage': stage, 'activate': activate}[args.action](args.restore_dir)
