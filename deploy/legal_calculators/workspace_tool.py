"""
title: Prokuratura AI legal calculators
description: Base calculation value (BHM) by date and procedural deadline arithmetic from curated tables.
version: 1.0.0
"""

import calendar
import datetime as dt
import json
import os
from pathlib import Path

# Tables are curated JSON files installed by deploy/native_assistant/manage.py refresh
# (source: deploy/legal_calculators/data/). Every result returns the row it used.
DATA_DIR = Path(os.getenv('LEGAL_CALCULATORS_DATA', '/app/backend/data/legal_calculators'))
UNITS = ('days', 'working_days', 'months', 'years')
MAX_DURATION = 3660


def load_table(name: str) -> dict:
    path = DATA_DIR / f'{name}.json'
    if not path.is_file():
        raise FileNotFoundError(f'{name} table is not installed')
    return json.loads(path.read_text(encoding='utf-8'))


def parse_date(value: str) -> dt.date:
    """ISO or dotted day-first dates ('2026-03-21', '21.03.2026'); empty means today (Tashkent)."""
    value = (value or '').strip()
    if not value:
        return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)).date()  # noqa: UP017 - py3.10 hosts
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Unrecognised date: {value!r}; use YYYY-MM-DD')


def row_for_date(rows: list, day: dt.date) -> dict | None:
    """Latest row whose effective_from is on or before the day; None before the first row or when
    the row carries a `verified_until` that the day exceeds (an unverified gap must not return a stale value)."""
    chosen = None
    for row in sorted(rows, key=lambda r: r['effective_from']):
        if dt.date.fromisoformat(row['effective_from']) <= day:
            chosen = row
    if chosen and chosen.get('verified_until') and day > dt.date.fromisoformat(chosen['verified_until']):
        return None
    return chosen


def calendar_days(holidays: dict, years) -> dict:
    """{date: (name, kind)} for the requested years from holidays.json."""
    days = {}
    for year in years:
        for entry in holidays.get('years', {}).get(str(year), []):
            days[dt.date.fromisoformat(entry['date'])] = (entry['name'], entry['kind'])
    return days


def is_working_day(day: dt.date, special: dict) -> bool:
    name_kind = special.get(day)
    if name_kind:
        return name_kind[1] == 'working_saturday'
    return day.weekday() < 5


def add_months(day: dt.date, months: int) -> dt.date:
    """Same day-of-month N months later, clamped to the last day of the target month."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def compute_deadline(start: dt.date, duration: int, unit: str, count_start_day: bool, special: dict) -> dict:
    """End date of a term plus the non-working days that shaped it."""
    first = start if count_start_day else start + dt.timedelta(days=1)
    skipped = []
    if unit == 'working_days':
        day, remaining = first - dt.timedelta(days=1), duration
        while remaining:
            day += dt.timedelta(days=1)
            if is_working_day(day, special):
                remaining -= 1
            elif day in special:
                skipped.append(day)
        end = day
    else:
        if unit == 'days':
            end = first + dt.timedelta(days=duration - 1)
        else:
            end = add_months(start, duration * (12 if unit == 'years' else 1))
        skipped = [d for d in special if first <= d <= end and special[d][1] != 'working_saturday']
    shifted_from = None
    if not is_working_day(end, special):
        shifted_from = end
        while not is_working_day(end, special):
            end += dt.timedelta(days=1)
    return {'end': end, 'shifted_from': shifted_from, 'skipped': sorted(skipped)}


class Tools:
    async def base_calculation_value(self, date: str = '', amount: float = 0) -> str:
        """Exact base calculation value (bazaviy hisoblash miqdori, BHM / БРВ) of Uzbekistan on a date,
        and optionally how many BHM a sum in so'm equals. Use for any amount expressed in BHM, thresholds,
        fines or "necha BHM" questions; never quote a BHM value from memory.
        :param date: Date the value is needed for (YYYY-MM-DD or DD.MM.YYYY); empty for today.
        :param amount: Optional sum in so'm to express in BHM multiples (0 = not needed).
        """
        try:
            table, day = load_table('bhm'), parse_date(date)
        except (FileNotFoundError, ValueError) as exc:
            return json.dumps({'error': str(exc)})
        row = row_for_date(table['rows'], day)
        if not row:
            return json.dumps({'error': f'The table has no verified BHM value for {day.isoformat()}.'})
        result = {'date': day.isoformat(), 'bhm_uzs': row['value'], 'effective_from': row['effective_from'],
                  'decree': row['decree'], 'source_url': row['source_url']}
        if row.get('min_wage_uzs'):
            result['min_wage_uzs'] = row['min_wage_uzs']
        if row.get('verification') == 'secondary':
            result['verification'] = 'Decree text not quoted from lex.uz; rests on official-press reports. Say so.'
        if amount:
            result['amount_uzs'] = amount
            result['amount_in_bhm'] = round(amount / row['value'], 4)
        latest = table['rows'][-1]
        if latest is not row:
            result['note'] = f'Current value since {latest["effective_from"]} is {latest["value"]} so\'m.'
        result['instruction'] = 'Cite the decree and source link; state the effective period of the value used.'
        return json.dumps(result, ensure_ascii=False)

    async def count_deadline(self, start_date: str, duration: int, unit: str = 'days',
                             count_start_day: bool = False) -> str:
        """Compute when a procedural or contractual term ends, using the holiday calendar of Uzbekistan.
        Default rule: the term starts the day after the event and, if the last day is a non-working day,
        ends on the next working day. Use for "qachon tugaydi", "muddat", "necha kun qoldi" questions.
        :param start_date: Date of the event the term is counted from (YYYY-MM-DD or DD.MM.YYYY).
        :param duration: Length of the term as a positive integer.
        :param unit: days (calendar), working_days, months or years.
        :param count_start_day: true only when the applicable rule counts the event day itself.
        """
        try:
            start, holidays = parse_date(start_date), load_table('holidays')
        except (FileNotFoundError, ValueError) as exc:
            return json.dumps({'error': str(exc)})
        if unit not in UNITS or not isinstance(duration, int) or not 0 < duration <= MAX_DURATION:
            return json.dumps({'error': f'unit must be one of {UNITS} and duration 1..{MAX_DURATION}'})
        years = range(start.year, start.year + (duration if unit == 'years' else duration // 200 + 2))
        special = calendar_days(holidays, years)
        outcome = compute_deadline(start, duration, unit, count_start_day, special)
        known = set(holidays.get('years', {}))
        missing = sorted({str(y) for y in range(start.year, outcome['end'].year + 1)} - known)
        result = {
            'start_date': start.isoformat(), 'duration': duration, 'unit': unit,
            'count_start_day': count_start_day, 'end_date': outcome['end'].isoformat(),
            'end_weekday': outcome['end'].strftime('%A'),
            'moved_from_non_working_day': outcome['shifted_from'].isoformat() if outcome['shifted_from'] else None,
            'non_working_days_in_term': [f'{d.isoformat()} {special[d][0]}' for d in outcome['skipped']],
            'holiday_calendar_source': holidays.get('source_url'),
            'instruction': 'State the rule assumed (start day not counted, shift to next working day) and, '
                           'if the user asks which code article applies, use the legal research tool.',
        }
        if missing:
            result['warning'] = f'No holiday calendar for {", ".join(missing)}: only weekends were skipped.'
        return json.dumps(result, ensure_ascii=False)
