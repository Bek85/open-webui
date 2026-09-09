// Run with Node 22.18+ (native TypeScript stripping); no dependencies required.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { toolResultFailed } from '../../src/lib/utils/tool-result.ts';
import { currentResearchStatus, statusKey } from '../../src/lib/utils/research-status.ts';

test('tool errors are not successful completions, including nested JSON and legacy strings', () => {
  for (const value of [{error:'service_unavailable'}, JSON.stringify({error:'service_unavailable'}), JSON.stringify(JSON.stringify({error:'service_unavailable'})), 'Error: Tool not found.']) {
    assert.equal(toolResultFailed(value), true);
  }
  for (const value of ['', null, '5', 'ordinary answer', {research:'answer'}, {error:false}, {error:null}]) {
    assert.equal(toolResultFailed(value), false);
  }
});

test('parallel calls sharing timestamps remain distinct and pending work wins', () => {
  const first = {research_id:'a', action:'reasoning', started_at:10, done:false};
  const second = {research_id:'b', action:'reasoning', started_at:10, ended_at:20, done:true};
  assert.notEqual(statusKey(first), statusKey(second));
  assert.equal(currentResearchStatus([first, second]), first);
  const finished = {...first, done:true, ended_at:30, error:true};
  assert.equal(currentResearchStatus([finished, second]), finished);
  assert.equal(currentResearchStatus([]), null);
  assert.equal(currentResearchStatus([{description:'legacy'}, second]).research_id, 'b');
});

test('all new captions have translations in all four supported locales', () => {
  const keys = ['{{NAME}} failed', 'Completed with errors', 'Legal research did not complete. No verified answer was returned.', 'Technical details', 'Researching legal sources…', 'Preparing legal analysis…', 'Legal analysis ready', 'Legal research failed', 'Unified assistant with documents, LexUz and Bosh prokuror buyruqlari.', 'LexUz / Bosh prokuror buyruqlari', 'Signed, permission-aware legal research for ProkuraturaAI.', 'Word / PDF / Excel', 'Private document generation; downloads expire after 30 days.', 'Encyclopedia search', 'Encyclopedia (offline Wikipedia)', 'Offline Uzbek and Russian Wikipedia search; no internet access.', 'Searching the encyclopedia…', 'Encyclopedia search complete', 'Encyclopedia search failed'];
  for (const locale of ['en-US', 'ru-RU', 'uz-Latn-UZ', 'uz-Cyrl-UZ']) {
    const text = readFileSync(new URL(`../../src/lib/i18n/locales/${locale}/translation.json`, import.meta.url), 'utf8');
    const translations = JSON.parse(text);
    for (const key of keys) {
      assert.ok(translations[key], `${locale}: ${key}`);
      assert.equal(text.split(JSON.stringify(key) + ':').length - 1, 1, `duplicate key: ${locale}: ${key}`);
    }
  }
});
