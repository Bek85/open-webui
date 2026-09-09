"""Install or remove the offline encyclopedia tool on the main model.

Run inside WebUI with deploy/native_assistant on PYTHONPATH.
"""

import argparse

from manage import COMPANION_TOOLS, MAIN_ID, PUBLIC_READ, ROOT, api, compose_system_prompt

TOOL_ID = 'prokuratura_encyclopedia'


def tool_form():
    dirname, name, description = COMPANION_TOOLS[TOOL_ID]
    return {
        'id': TOOL_ID,
        'name': name,
        'content': (ROOT.parent / dirname / 'workspace_tool.py').read_text(),
        'meta': {'description': description},
        'access_grants': PUBLIC_READ,
    }


def activate():
    """Idempotent: create/update the public tool, bind it as required on the main model, recompose the prompt."""
    installed = {t['id'] for t in api('/api/v1/tools/')}
    if TOOL_ID in installed:
        api('/api/v1/tools/id/' + TOOL_ID + '/update', tool_form())
    else:
        api('/api/v1/tools/create', tool_form())
    model = api('/api/v1/models/model?id=' + MAIN_ID)
    for key in ('toolIds', 'requiredToolIds'):
        model['meta'][key] = list(dict.fromkeys([*(model['meta'].get(key) or []), TOOL_ID]))
    model['params'] = {**(model.get('params') or {}), 'system': compose_system_prompt(model['meta']['toolIds'])}
    result = api('/api/v1/models/model/update', model)
    assert TOOL_ID in result['meta']['requiredToolIds']
    print('Encyclopedia tool active on', MAIN_ID)


def deactivate():
    """Unbind the tool from the main model, recompose the prompt, delete the tool. Chats are untouched."""
    model = api('/api/v1/models/model?id=' + MAIN_ID)
    for key in ('toolIds', 'requiredToolIds'):
        model['meta'][key] = [t for t in (model['meta'].get(key) or []) if t != TOOL_ID]
    model['params'] = {**(model.get('params') or {}), 'system': compose_system_prompt(model['meta']['toolIds'])}
    api('/api/v1/models/model/update', model)
    if TOOL_ID in {t['id'] for t in api('/api/v1/tools/')}:
        api('/api/v1/tools/id/' + TOOL_ID + '/delete', method='DELETE')
    print('Encyclopedia tool removed from', MAIN_ID)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['activate', 'deactivate'])
    {'activate': activate, 'deactivate': deactivate}[parser.parse_args().action]()
