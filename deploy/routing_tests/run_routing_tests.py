"""Routing test suite: does each representative request reach the right tool?

Two modes, both against the live model:
  classifier  temperature-0 route classification only (the deterministic first hop; ~1 s per case)
  e2e         a real chat turn through Open WebUI, checking which tool was actually used

Run inside the WebUI container with deploy/native_assistant on PYTHONPATH:
  python run_routing_tests.py --mode classifier
  python run_routing_tests.py --mode e2e --category encyclopedia --limit 5
Exit code 1 when any category falls below its recorded baseline; --update-baseline records the current rates.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASE_DIR = ROOT / 'cases'
BASELINE = ROOT / 'baseline.json'


def load_categories(names=None):
    categories = []
    for path in sorted(CASE_DIR.glob('*.json')):
        data = json.loads(path.read_text())
        if not names or data['category'] in names:
            categories.append(data)
    return categories


def llm_endpoint():
    """Base model endpoint from the WebUI provider config, like the other probes."""
    from manage import api

    config = api('/openai/config')
    return config['OPENAI_API_BASE_URLS'][0].rstrip('/'), config['OPENAI_API_KEYS'][0]


def classify(text, base_url, key, system_prompt):
    from open_webui.utils.legal_fast_path import parse_route

    body = {
        'model': 'ProkuraturaAI',
        'stream': False,
        'temperature': 0,
        'max_tokens': 10,
        'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': text[:800]}],
    }
    request = urllib.request.Request(
        base_url + '/chat/completions',
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)
    return parse_route(data['choices'][0]['message']['content'])


def run_classifier(categories, limit):
    from open_webui.utils.legal_fast_path import CLASSIFY_SYSTEM

    base_url, key = llm_endpoint()
    rates = {}
    for category in categories:
        cases = category['cases'][:limit] if limit else category['cases']
        hits = 0
        for case in cases:
            route = classify(case['text'], base_url, key, CLASSIFY_SYSTEM)
            ok = route == category['route']
            hits += ok
            mark = 'OK  ' if ok else 'MISS'
            print(f'{mark} {category["category"]:<18} {route:<10} [{case["script"]}] {case["text"][:60]}', flush=True)
        rates[category['category']] = hits / max(len(cases), 1)
    return rates


def run_e2e(categories, limit):
    from chat_turn import turn

    rates = {}
    for category in categories:
        cases = category['cases'][:limit] if limit else category['cases']
        history = category.get('history') or []
        hits = 0
        for case in cases:
            result = turn(history + [{'role': 'user', 'content': case['text']}])
            ok = result.used(category['tool']) and not result.error
            hits += ok
            first = result.first_text and round(result.first_text, 1)
            print(
                f'{"OK  " if ok else "MISS"} {category["category"]:<18} calls={[n for n, _ in result.calls]} '
                f'legal={result.legal_stream} wiki={result.wiki_sources} first={first}s total={result.total:.0f}s '
                f'err={result.error} [{case["script"]}] {case["text"][:50]}',
                flush=True,
            )
        rates[category['category']] = hits / max(len(cases), 1)
    return rates


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', choices=['classifier', 'e2e'], default='classifier')
    parser.add_argument('--category', action='append', help='limit to a category (repeatable)')
    parser.add_argument('--limit', type=int, default=0, help='cases per category (0 = all)')
    parser.add_argument('--update-baseline', action='store_true')
    args = parser.parse_args()
    categories = load_categories(args.category)
    rates = run_classifier(categories, args.limit) if args.mode == 'classifier' else run_e2e(categories, args.limit)
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    recorded = baseline.get(args.mode, {})
    failed = False
    for name, rate in rates.items():
        floor = recorded.get(name)
        verdict = 'no baseline' if floor is None else ('ok' if rate >= floor else f'BELOW baseline {floor:.2f}')
        failed |= floor is not None and rate < floor
        print(f'{name:<18} {rate:.2f}  {verdict}')
    if args.update_baseline and not args.limit and not args.category:
        baseline[args.mode] = {k: round(v, 2) for k, v in rates.items()}
        BASELINE.write_text(json.dumps(baseline, indent=2) + '\n')
        print('baseline updated:', BASELINE)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
