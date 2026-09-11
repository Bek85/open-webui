# Legal calculators (phase 04)

Deterministic tools for the two numbers the model must never guess: the base
calculation value (bazaviy hisoblash miqdori, BHM) on a date and the end of a
term. Pure arithmetic over curated tables; the law that decides which term or
threshold applies stays with the legal research tool.

| Piece | Where |
|---|---|
| tool code | `workspace_tool.py` (installed into the WebUI database, id `prokuratura_legal_calculators`) |
| tables | `data/bhm.json`, `data/holidays.json`; copied to `/app/backend/data/legal_calculators/` by `manage.py refresh` |
| prompt text | `instructions.txt`, appended by `native_assistant/manage.py refresh` when the tool is bound |
| routing | classifier class `calc` narrows the turn to these tools with `tool_choice=required` (`backend/open_webui/utils/legal_fast_path.py`) |
| tests | `tests/test_workspace_tool.py` (fixture tables plus integrity checks on the shipped data); `routing_tests/cases/legal-calculators.json` |

## Tools

- `base_calculation_value(date='', amount=0)`: BHM on the date (today by default),
  the decree and link, the minimum wage where the same decree sets it, and
  `amount_in_bhm` when a sum is given. Refuses dates the table does not cover
  instead of returning a neighbouring value.
- `count_deadline(start_date, duration, unit='days', count_start_day=False)`:
  end date of a term in calendar days, working days, months or years. Default rule:
  the term starts the day after the event, and a last day that is a rest day or
  holiday moves the end to the next working day. That is Article 314 of the
  Criminal Procedure Code and Article 152 of the Civil Procedure Code; custody
  terms (Article 315) count from the moment of the measure, hence `count_start_day`.
  The result lists the non-working days inside the term and warns when the holiday
  calendar does not cover a year.

## Data provenance

`bhm.json` rows quote the decree clause (`bazaviy hisoblash miqdori — N so'm etib
belgilansin`) and its effective date from lex.uz. Two rows (2021-02-01: 245 000,
2021-09-01: 270 000) could not be quoted because the amending decree rewrote the
original clause; they rest on consistent official-press reports and are flagged
`verification: secondary`, which the tool passes on to the model. The 2019 row is
closed with `verified_until` so the gap before them errors rather than answering.

`holidays.json` combines Article 208 of the Labour Code (fixed holidays and the
rule that a rest day coinciding with a holiday moves to the next working day) with
the yearly presidential decisions on additional rest days, transfers and the two
religious holidays, one source link per entry. Saturdays made working days to
compensate a transfer are `working_saturday` entries.

## Update path (legal team)

1. New BHM decree: append a row to `data/bhm.json` with `effective_from`, `value`,
   `min_wage_uzs` if set by the same decree, the quoted clause in `decree`, and the
   lex.uz link.
2. New year: add the year to `data/holidays.json` from the December decree, then the
   Ramazon and Qurbon decisions when published.
3. Run the tests, then from the repo root:
   ```sh
   docker cp deploy/. open-webui:/tmp/deploy/
   docker exec -e PYTHONPATH=/app/backend:/tmp/deploy/native_assistant -w /app/backend open-webui \
     python /tmp/deploy/native_assistant/manage.py refresh
   ```
   No image rebuild: tables and tool code live outside the image.

## Install / remove

```sh
docker cp deploy/. open-webui:/tmp/deploy/
docker exec -e PYTHONPATH=/app/backend:/tmp/deploy/native_assistant -w /app/backend open-webui \
  python /tmp/deploy/legal_calculators/manage_legal_calculators.py activate    # or deactivate
```

`activate` is idempotent: it installs the tables, creates or updates the public
tool, binds it as a required tool on the main model and recomposes the system
prompt. Fine ranges per article (step 3 of the phase plan) are not included
until the legal team curates that table.
