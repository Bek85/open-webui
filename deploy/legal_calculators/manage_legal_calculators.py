"""Install or remove the legal calculators tool on the main model.

Run inside WebUI with deploy/native_assistant on PYTHONPATH. `activate` also copies
the curated tables into the WebUI data volume (as `manage.py refresh` does).
"""

import argparse

from manage import activate_companion, deactivate_companion, install_calculator_tables

TOOL_ID = 'prokuratura_legal_calculators'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['activate', 'deactivate'])
    if parser.parse_args().action == 'activate':
        install_calculator_tables()
        activate_companion(TOOL_ID)
    else:
        deactivate_companion(TOOL_ID)
