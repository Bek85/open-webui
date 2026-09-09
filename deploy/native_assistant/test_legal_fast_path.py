"""Offline tests for the legal fast path (run with PYTHONPATH=/app/backend)."""

import asyncio
import json
import unittest

from open_webui.utils import encyclopedia_context as enc
from open_webui.utils import legal_fast_path as lfp
from open_webui.utils import legal_specialist_stream as lss


async def frames_from(lines):
    for line in lines:
        yield line


def parse_stream(chunks):
    events, text, finish = [], [], None
    for chunk in chunks:
        payload = chunk.decode().removeprefix('data: ').strip()
        if payload == '[DONE]':
            finish = 'done'
            continue
        data = json.loads(payload)
        if 'event' in data:
            events.append(data['event'])
        else:
            delta = data['choices'][0]['delta']
            text.append(delta.get('content', ''))
            finish = data['choices'][0].get('finish_reason') or finish
    return events, ''.join(text), finish


def collect(gen):
    async def run():
        return [chunk async for chunk in gen]

    return asyncio.run(run())


class RouteParsing(unittest.TestCase):
    def test_one_word_answers(self):
        self.assertEqual(lfp.parse_route(' LexUz\n'), 'lexuz')
        self.assertEqual(lfp.parse_route('prosecutor'), 'prosecutor')
        self.assertEqual(lfp.parse_route('general'), 'general')
        self.assertEqual(lfp.parse_route('wiki'), 'wiki')
        self.assertEqual(lfp.parse_route('file'), 'file')
        self.assertEqual(lfp.parse_route(''), 'general')
        self.assertEqual(lfp.parse_route(None), 'general')


class Eligibility(unittest.TestCase):
    model = {'info': {'meta': {}}}

    def test_ui_legal_turn_without_files(self):
        self.assertTrue(lfp.is_fast_path_candidate({'session_id': 's'}, self.model, ['research_uzbek_law']))

    def test_attachments_and_api_calls_keep_native_tools(self):
        self.assertFalse(
            lfp.is_fast_path_candidate({'session_id': 's', 'files': [{'id': 'f'}]}, self.model, ['research_uzbek_law'])
        )
        self.assertFalse(lfp.is_fast_path_candidate({}, self.model, ['research_uzbek_law']))
        self.assertFalse(
            lfp.is_fast_path_candidate({'session_id': 's', 'direct': True}, self.model, ['research_uzbek_law'])
        )
        self.assertFalse(lfp.is_fast_path_candidate({'session_id': 's'}, self.model, ['create_document']))
        self.assertFalse(
            lfp.is_fast_path_candidate(
                {'session_id': 's'}, {'info': {'meta': {'legalFastPath': False}}}, ['research_uzbek_law']
            )
        )

    def test_toggled_features_keep_the_model_in_charge(self):
        metadata = {'session_id': 's', 'features': {'web_search': True}}
        self.assertFalse(lfp.is_fast_path_candidate(metadata, self.model, ['research_uzbek_law']))

    def test_image_parts_are_not_plain_text_questions(self):
        image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAA'}}
        self.assertIsNone(
            lfp.plain_text_question([{'role': 'user', 'content': [{'type': 'text', 'text': 'q'}, image]}])
        )
        self.assertEqual(
            lfp.plain_text_question([{'role': 'user', 'content': [{'type': 'text', 'text': ' q '}]}]), ' q '
        )
        self.assertEqual(lfp.plain_text_question([{'role': 'user', 'content': 'q'}]), 'q')
        self.assertIsNone(lfp.plain_text_question([{'role': 'user', 'content': '  '}]))

    def test_history_is_text_only_and_bounded(self):
        messages = [{'role': 'system', 'content': 'sys'}]
        messages += [{'role': 'user', 'content': [{'type': 'text', 'text': f'q{i}'}]} for i in range(20)]
        history = lfp.specialist_messages(messages)
        self.assertEqual(len(history), lfp.MAX_HISTORY_MESSAGES)
        self.assertEqual(history[-1], {'role': 'user', 'content': 'q19'})


class ForcedFileTools(unittest.TestCase):
    """Exports must not depend on sampling: the file route forces the call."""

    def form(self):
        return {
            'tools': [
                {'type': 'function', 'function': {'name': 'research_uzbek_law'}},
                {'type': 'function', 'function': {'name': 'create_document'}},
                {'type': 'function', 'function': {'name': 'create_spreadsheet'}},
            ]
        }

    def test_only_file_tools_remain_and_a_call_is_required(self):
        form = self.form()
        self.assertTrue(lfp.force_file_tools(form, ['research_uzbek_law', 'create_document', 'create_spreadsheet']))
        self.assertEqual(
            [spec['function']['name'] for spec in form['tools']], ['create_document', 'create_spreadsheet']
        )
        self.assertEqual(form['tool_choice'], 'required')

    def test_unbound_file_tools_leave_the_turn_alone(self):
        form = self.form()
        self.assertFalse(lfp.force_file_tools(form, ['research_uzbek_law']))
        self.assertNotIn('tool_choice', form)
        self.assertEqual(len(form['tools']), 3)

    def test_file_route_plan_keeps_the_model_answering(self):
        # 'file' is a context-shaping route like 'wiki': no corpus, so no specialist relay.
        self.assertIsNone(lfp.CORPUS_BY_ROUTE.get('file'))


class Relay(unittest.TestCase):
    def test_status_content_and_sources(self):
        summary = {'action': 'summary', 'description': 'Tahlil', 'done': True, 'started_at': 1, 'ended_at': 9}
        lines = [
            ('status', json.dumps({'action': 'knowledge_search', 'done': True, 'items': []})),
            ('message', 'Javob: [211-modda](https://lex.uz/docs/1) '),
            ('message', 'davomi.'),
            ('status', json.dumps(summary)),
            ('done', '[DONE]'),
        ]
        events, text, finish = parse_stream(collect(lss.relay_frames(frames_from(lines), 'm', 'lex_uz', 'savol')))
        self.assertEqual(text, 'Javob: [211-modda](https://lex.uz/docs/1) davomi.')
        self.assertEqual(finish, 'done')
        self.assertEqual([e['type'] for e in events].count('source'), 1)
        statuses = [e['data'] for e in events if e['type'] == 'status']
        self.assertEqual(statuses[0]['description'], 'Researching legal sources…')
        self.assertTrue(statuses[1]['done'] and not statuses[1]['error'])  # placeholder closed on first frame
        self.assertIn({'action': 'knowledge_search', 'done': True, 'items': []}, statuses)
        # The specialist's summary stays last and untouched, as with the legacy pipeline.
        self.assertEqual(statuses[-1], summary)

    def test_incomplete_stream_is_reported_not_trusted(self):
        lines = [('message', 'partial answer')]
        events, text, _ = parse_stream(collect(lss.relay_frames(frames_from(lines), 'm', 'prosecutor', 'савол')))
        self.assertTrue(text.startswith('partial answer'))
        self.assertIn('алоқа узилди', text)
        self.assertEqual(events[-1]['data']['description'], 'Legal research failed')
        self.assertTrue(events[-1]['data']['error'])
        self.assertFalse([e for e in events if e['type'] == 'source'])

    def test_empty_stream_gives_user_facing_failure(self):
        events, text, _ = parse_stream(
            collect(lss.relay_frames(frames_from([('done', '[DONE]')]), 'm', 'lex_uz', 'savol'))
        )
        self.assertIn('aloqa uzildi', text)
        self.assertEqual(events[-1]['data']['description'], 'Legal research failed')

    def test_open_steps_close_on_failure(self):
        lines = [('status', json.dumps({'action': 'knowledge_search', 'done': False, 'started_at': 5}))]
        events, _, _ = parse_stream(collect(lss.relay_frames(frames_from(lines), 'm', 'lex_uz', 'savol')))
        closed = [e['data'] for e in events if e['data'].get('action') == 'knowledge_search' and e['data'].get('done')]
        self.assertEqual(len(closed), 1)
        self.assertTrue(closed[0]['error'] and closed[0]['ended_at'])
        self.assertEqual(events[-1]['data']['description'], 'Legal research failed')

    def test_finalize_runs_even_when_stream_breaks(self):
        closed = []

        async def finalize():
            closed.append(True)

        async def broken():
            yield ('message', 'x')
            raise lss.aiohttp.ClientPayloadError('cut')

        events, text, _ = parse_stream(collect(lss.relay_frames(broken(), 'm', 'lex_uz', 'savol', finalize)))
        self.assertEqual(closed, [True])
        self.assertEqual(events[-1]['data']['description'], 'Legal research failed')

    def test_finalize_runs_when_consumer_closes_early(self):
        closed = []

        async def finalize():
            closed.append(True)

        async def run():
            gen = lss.relay_frames(frames_from([('message', 'x')] * 5), 'm', 'lex_uz', 'savol', finalize)
            await gen.__anext__()
            await gen.aclose()

        asyncio.run(run())
        self.assertEqual(closed, [True])


class Bibliography(unittest.TestCase):
    def test_cards_follow_bibliography_numbers_not_appearance(self):
        text = (
            'Matn [2] va [1].\n\nInline [FK](https://lex.uz/uz/docs/-3) link.\n\n### Manbalar\n\n'
            '1. [JK 109](https://lex.uz/uz/docs/-1)\n2. [JK 104](https://lex.uz/uz/docs/-2)\n'
        )
        self.assertEqual(
            [c['source']['id'] for c in lss.bibliography_sources(text)],
            ['https://lex.uz/uz/docs/-1', 'https://lex.uz/uz/docs/-2'],
        )

    def test_gap_in_numbering_yields_no_cards(self):
        text = 'Manbalar\n1. [A](https://lex.uz/uz/docs/-1)\n3. [C](https://lex.uz/uz/docs/-3)\n'
        self.assertEqual(lss.bibliography_sources(text), [])

    def test_without_a_bibliography_block_links_keep_appearance_order(self):
        text = 'A [x](https://lex.uz/uz/docs/-9) B [y](https://lex.uz/uz/docs/-8) [x](https://lex.uz/uz/docs/-9)'
        self.assertEqual(
            [c['source']['id'] for c in lss.bibliography_sources(text)],
            ['https://lex.uz/uz/docs/-9', 'https://lex.uz/uz/docs/-8'],
        )


class EncyclopediaContext(unittest.TestCase):
    result = {
        'article': {
            'title': 'Samarqand',
            'url': 'https://ai.example/wiki/content/b/Samarqand',
            'text': 'Qadimiy shahar.',
        },
        'results': [
            {'title': 'Samarqand', 'url': 'https://ai.example/wiki/content/b/Samarqand', 'snippet': 'dup'},
            {'title': 'Registon', 'url': 'https://ai.example/wiki/content/b/Registon', 'snippet': 'Maydon.'},
            {'title': 'Empty', 'url': 'https://ai.example/wiki/content/b/E', 'snippet': ''},
        ],
    }

    def test_docs_article_first_unique_by_url(self):
        docs = enc.encyclopedia_docs(self.result)
        self.assertEqual([d['metadata']['source'].rsplit('/', 1)[1] for d in docs], ['Samarqand', 'Registon'])
        self.assertEqual(docs[0]['content'], 'Qadimiy shahar.')

    def test_attach_adds_a_docs_file_item(self):
        async def fake(query):
            return json.dumps(self.result)

        form = {'files': None}
        attached = asyncio.run(
            enc.attach_encyclopedia_context(form, {'search_encyclopedia': {'callable': fake}}, 'Samarqand haqida')
        )
        self.assertTrue(attached)
        self.assertEqual(form['files'][0]['type'], 'web_search')
        self.assertEqual(len(form['files'][0]['docs']), 2)

    def test_errors_and_missing_tool_attach_nothing(self):
        async def failing(query):
            return json.dumps({'error': 'service_unavailable'})

        form = {}
        self.assertFalse(
            asyncio.run(enc.attach_encyclopedia_context(form, {'search_encyclopedia': {'callable': failing}}, 'x'))
        )
        self.assertFalse(asyncio.run(enc.attach_encyclopedia_context(form, {}, 'x')))
        self.assertNotIn('files', form)


class Identity(unittest.TestCase):
    def test_headers_require_user_and_secret(self):
        headers = lss.identity_headers({'id': 'u|1', 'email': 'a@b', 'role': 'user'}, 'c', 'secret')
        self.assertEqual(headers['X-User-Id'], 'u1')
        self.assertEqual(len(headers['X-Auth-Sig']), 64)
        with self.assertRaises(ValueError):
            lss.identity_headers({'id': 'u'}, 'c', '')


if __name__ == '__main__':
    unittest.main()
