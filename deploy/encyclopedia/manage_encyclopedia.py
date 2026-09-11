"""Install or remove the offline encyclopedia tool on the main model.

Run inside WebUI with deploy/native_assistant on PYTHONPATH.
"""

import argparse

from manage import activate_companion, deactivate_companion

TOOL_ID = 'prokuratura_encyclopedia'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['activate', 'deactivate'])
    action = parser.parse_args().action
    (activate_companion if action == 'activate' else deactivate_companion)(TOOL_ID)
