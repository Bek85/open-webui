import asyncio
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from aiohttp import ClientPayloadError, web
from legal_research import Tools, bibliography, identity_headers, safe_source, sse_frames


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.status = 200
        self.body = 'event: message\ndata: Verified [law](https://lex.uz/docs/1).\n\nevent: done\ndata: [DONE]\n\n'

        async def handler(request):
            self.requests.append((dict(request.headers), await request.json(), request.path))
            return web.Response(text=self.body, status=self.status, content_type='text/event-stream')

        app = web.Application()
        app.router.add_post('/{corpus}/stream', handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.tool = Tools()
        self.tool.valves.RAG_BASE_URL = f'http://127.0.0.1:{port}'
        self.secret = patch.dict('os.environ', {'MCP_AUTH_SECRET': 'test-only'})
        self.secret.start()
        self.events = []

    async def asyncTearDown(self):
        self.secret.stop()
        await self.runner.cleanup()

    async def emit(self, event):
        self.events.append(event)

    async def research(self, query='Mehnat taʼtili qancha?', corpus='lex_uz'):
        result = await self.tool._research(
            corpus,
            query,
            {'id': 'u1', 'role': 'user', 'email': 'u@example.test'},
            {'chat_id': 'chat1', 'files': ['must-not-forward']},
            self.emit,
        )
        return json.loads(result)

    async def test_focused_payload_signed_identity_and_bibliography(self):
        result = await self.research()
        headers, payload, path = self.requests[0]
        self.assertEqual(path, '/lex_uz/stream')
        self.assertEqual(payload, {'messages': [{'role': 'user', 'content': 'Mehnat taʼtili qancha?'}], 'stream': True})
        canonical = '|'.join(('v1', 'u1', 'u@example.test', 'user', 'chat1', headers['X-Auth-Ts']))
        self.assertEqual(headers['X-Auth-Sig'], hmac.new(b'test-only', canonical.encode(), hashlib.sha256).hexdigest())
        self.assertIn('https://lex.uz/docs/1', result['research'])
        self.assertTrue(self.events[-1]['data']['done'])
        self.assertFalse(self.events[-1]['data']['error'])

    async def test_denied_not_retried_or_rerouted(self):
        self.status = 403
        result = await self.research(corpus='prosecutor')
        self.assertEqual(result['error'], 'access_denied')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][2], '/prosecutor/stream')
        self.assertTrue(self.events[-1]['data']['error'])

    async def test_bad_queries_never_leave_tool(self):
        for query in ('', ' ', 'x' * 12001, ['image']):
            self.assertEqual((await self.research(query))['error'], 'invalid_query')
        self.assertEqual(self.requests, [])

    async def test_missing_identity_fails_closed(self):
        with patch.dict('os.environ', {'MCP_AUTH_SECRET': ''}):
            self.assertEqual((await self.research())['error'], 'identity_unavailable')
        with self.assertRaises(ValueError):
            identity_headers({}, 'chat', 'secret')
        self.assertEqual(self.requests, [])

    async def test_status_events_and_malformed_status(self):
        self.body = (
            'event: status\ndata: not-json\n\nevent: status\ndata: {"action":"knowledge_search",'
            '"items":[{"link":"https://lex.uz/1","title":"Law"}],"done":true}\n\n'
            'event: message\ndata: answer\n\nevent: done\ndata: [DONE]\n\n'
        )
        result = await self.research()
        self.assertEqual(result['search_results'][0]['title'], 'Law')
        self.assertTrue(any(e['data'].get('action') == 'knowledge_search' for e in self.events))

    async def test_errors_do_not_leak_backend_body(self):
        self.body = 'secret-internal-debug-details'
        for status, expected in ((422, 'invalid_request'), (500, 'service_unavailable'), (401, 'access_denied')):
            self.status = status
            result = await self.research()
            self.assertEqual(result['error'], expected)
            self.assertNotIn(self.body, json.dumps(result))

    async def test_stream_error_discards_partial_answer(self):
        self.body = 'event: message\ndata: incomplete\n\nevent: error\ndata: internal-error\n\n'
        self.assertEqual((await self.research())['error'], 'research_failed')

    async def test_incomplete_stream_is_not_success(self):
        self.body = 'event: message\ndata: incomplete answer\n\n'
        self.assertEqual((await self.research())['error'], 'incomplete_stream')
        self.assertTrue(self.events[-1]['data']['error'])

    async def test_summary_does_not_finish_research_and_parallel_ids_are_distinct(self):
        self.body = (
            'event: status\ndata: {"action":"summary","description":"Topic","done":true,"started_at":1}\n\n'
            'event: message\ndata: answer\n\nevent: done\ndata: [DONE]\n\n'
        )
        await asyncio.gather(self.research(), self.research())
        statuses = [e['data'] for e in self.events]
        ids = {s['research_id'] for s in statuses}
        self.assertEqual(len(ids), 2)
        self.assertFalse(any(s['action'] == 'summary' for s in statuses))
        for rid in ids:
            steps = [s for s in statuses if s['research_id'] == rid]
            self.assertTrue(any(s['description'] == 'Preparing legal analysis…' and not s['done'] for s in steps))
            self.assertEqual(steps[-1]['description'], 'Legal analysis ready')
            self.assertFalse(steps[-1]['error'])
            latest = {(s['action'], s['started_at']): s for s in steps}
            self.assertTrue(all(s['done'] for s in latest.values()))

    async def test_transport_failure_logs_type_not_sensitive_exception_message(self):
        async def broken_stream(content):
            yield 'status', '{"action":"knowledge_search","started_at":1,"done":false}'
            raise ClientPayloadError('secret-backend-details')

        with (
            patch('legal_research.sse_frames', broken_stream),
            self.assertLogs('legal_research', level='WARNING') as logs,
        ):
            result = await self.research()
        self.assertEqual(result['error'], 'service_unavailable')
        self.assertIn('ClientPayloadError', str(logs.output))
        self.assertNotIn('secret-backend-details', str(logs.output))
        self.assertNotIn('u@example.test', str(logs.output))
        self.assertTrue(self.events[-2]['data']['done'])
        self.assertTrue(self.events[-2]['data']['error'])
        self.assertTrue(self.events[-1]['data']['error'])

    async def test_empty_and_oversized_results(self):
        for body, expected in (('', 'empty_result'), ('x' * 120001, 'result_too_large')):
            # Keep individual SSE lines below aiohttp's line limit.
            self.body = ''.join(
                'event: message\ndata: ' + body[i : i + 10000] + '\n\n' for i in range(0, len(body), 10000)
            )
            self.assertEqual((await self.research())['error'], expected)

    async def test_parser_multiline_unicode_crlf_and_last_frame(self):
        async def content():
            for line in (
                ': ping\r\n',
                'event: status\r\n',
                'data: {\r\n',
                'data: "title":"Қонун"}\r\n',
                '\r\n',
                'data: last',
            ):
                yield line.encode()

        self.assertEqual(
            [x async for x in sse_frames(content())], [('status', '{\n"title":"Қонун"}'), ('message', 'last')]
        )

    def test_identity_sanitization_and_source_urls(self):
        headers = identity_headers({'id': 'u|\n1', 'role': 'user'}, 'chat\r|1', 'secret')
        self.assertEqual(headers['X-User-Id'], 'u1')
        self.assertEqual(headers['X-Chat-Id'], 'chat1')
        self.assertIsNone(safe_source({'link': 'javascript:alert(1)'}))

    def test_only_report_bibliography_is_cited(self):
        result = bibliography('[Law](https://lex.uz/docs/1) [Law](https://lex.uz/docs/1) [unsafe](javascript:alert)')
        self.assertEqual(result, [{'title': 'Law', 'url': 'https://lex.uz/docs/1', 'content': 'Law'}])


if __name__ == '__main__':
    unittest.main()
