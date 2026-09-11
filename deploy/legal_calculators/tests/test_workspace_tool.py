"""Offline tests for the legal calculators: fixture tables plus integrity checks on the shipped data."""

import asyncio
import datetime as dt
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = tempfile.mkdtemp()
os.environ['LEGAL_CALCULATORS_DATA'] = FIXTURE
spec = importlib.util.spec_from_file_location('legal_calculators', ROOT / 'workspace_tool.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

BHM = {
    'unit': 'UZS',
    'rows': [
        {'effective_from': '2019-09-01', 'value': 223000, 'decree': 'D-1', 'source_url': 'https://lex.uz/1',
         'verified_until': '2021-01-31'},
        {'effective_from': '2024-10-01', 'value': 375000, 'decree': 'D-2', 'source_url': 'https://lex.uz/2',
         'min_wage_uzs': 1155000},
    ],
}
HOLIDAYS = {
    'source_url': 'https://lex.uz/h',
    'years': {
        '2026': [
            {'date': '2026-01-01', 'name': 'Yangi yil', 'kind': 'holiday'},
            {'date': '2026-01-02', 'name': 'Ko‘chirilgan dam olish kuni', 'kind': 'transferred_rest_day'},
            {'date': '2026-01-10', 'name': 'Ish kuni (shanba)', 'kind': 'working_saturday'},
            {'date': '2026-03-20', 'name': 'Ramazon hayiti', 'kind': 'holiday'},
        ]
    },
}
Path(FIXTURE, 'bhm.json').write_text(json.dumps(BHM))
Path(FIXTURE, 'holidays.json').write_text(json.dumps(HOLIDAYS))


def run(coro):
    return json.loads(asyncio.run(coro))


class BaseCalculationValue(unittest.TestCase):
    def test_value_on_date_with_row_and_current_note(self):
        result = run(tool.Tools().base_calculation_value('2020-05-05', amount=1_115_000))
        self.assertEqual((result['bhm_uzs'], result['effective_from'], result['decree']), (223000, '2019-09-01', 'D-1'))
        self.assertEqual(result['amount_in_bhm'], 5.0)
        self.assertIn('375000', result['note'])

    def test_latest_row_has_no_note_and_dotted_dates_parse(self):
        result = run(tool.Tools().base_calculation_value('15.11.2024'))
        self.assertEqual((result['bhm_uzs'], result['min_wage_uzs']), (375000, 1155000))
        self.assertNotIn('note', result)

    def test_before_first_row_gap_and_bad_date_are_errors(self):
        calc = tool.Tools()
        self.assertIn('no verified BHM value for 2018-01-01', run(calc.base_calculation_value('2018-01-01'))['error'])
        self.assertIn('no verified BHM value for 2021-06-01', run(calc.base_calculation_value('2021-06-01'))['error'])
        self.assertEqual(run(tool.Tools().base_calculation_value('2021-01-31'))['bhm_uzs'], 223000)
        self.assertIn('Unrecognised date', run(tool.Tools().base_calculation_value('yesterday'))['error'])


class CountDeadline(unittest.TestCase):
    def test_calendar_days_skip_start_day_and_shift_off_holiday(self):
        # 10 days from 2025-12-22: day 1 is 12-23, day 10 is 2026-01-01 (holiday) -> 01-02 is a
        # transferred rest day, 01-03/04 weekend -> ends Monday 2026-01-05.
        result = run(tool.Tools().count_deadline('2025-12-22', 10))
        self.assertEqual(result['end_date'], '2026-01-05')
        self.assertEqual(result['moved_from_non_working_day'], '2026-01-01')
        self.assertIn('2026-01-01 Yangi yil', result['non_working_days_in_term'])
        self.assertIn('2025', result['warning'])  # fixture has no 2025 calendar

    def test_working_days_honour_working_saturday_and_holidays(self):
        # From 2026-01-05 (Mon): 01-06..01-09 are 4 working days, Sat 01-10 is a working Saturday = 5.
        result = run(tool.Tools().count_deadline('2026-01-05', 5, unit='working_days'))
        self.assertEqual(result['end_date'], '2026-01-10')
        self.assertIsNone(result['moved_from_non_working_day'])

    def test_months_clamp_to_month_end_and_count_start_day_option(self):
        self.assertEqual(run(tool.Tools().count_deadline('2026-01-31', 1, unit='months'))['end_date'], '2026-03-02')
        self.assertEqual(tool.add_months(dt.date(2026, 1, 31), 1), dt.date(2026, 2, 28))
        inclusive = run(tool.Tools().count_deadline('2026-02-02', 3, count_start_day=True))
        self.assertEqual(inclusive['end_date'], '2026-02-04')

    def test_invalid_unit_or_duration(self):
        self.assertIn('error', run(tool.Tools().count_deadline('2026-01-01', 0)))
        self.assertIn('error', run(tool.Tools().count_deadline('2026-01-01', 5, unit='weeks')))


class ShippedData(unittest.TestCase):
    """The real tables must be internally consistent; values themselves are verified against lex.uz by hand."""

    def load(self, name):
        path = ROOT / 'data' / f'{name}.json'
        if not path.is_file():
            self.skipTest(f'{name}.json not curated yet')
        return json.loads(path.read_text(encoding='utf-8'))

    def test_bhm_rows_sorted_positive_and_sourced(self):
        rows = self.load('bhm')['rows']
        dates = [r['effective_from'] for r in rows]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(dates), len(set(dates)))
        for row in rows:
            dt.date.fromisoformat(row['effective_from'])
            self.assertIsInstance(row['value'], int)
            self.assertGreater(row['value'], 0)
            self.assertTrue(row['decree'] and row['source_url'].startswith('https://'))
            if row.get('verified_until'):
                self.assertGreater(row['verified_until'], row['effective_from'])
            self.assertIn(row.get('verification', 'primary'), ('primary', 'secondary'))

    def test_holiday_entries_match_their_year_and_kinds(self):
        table = self.load('holidays')
        self.assertTrue(table.get('source_url', '').startswith('https://'))
        for year, entries in table['years'].items():
            for entry in entries:
                self.assertTrue(entry['date'].startswith(year), entry)
                self.assertIn(entry['kind'], ('holiday', 'transferred_rest_day', 'working_saturday'), entry)
                self.assertTrue(entry['name'])


if __name__ == '__main__':
    unittest.main()
