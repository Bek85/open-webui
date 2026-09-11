"""Unit tests for whole-document context (run inside the WebUI image: backend deps needed)."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import open_webui.utils.document_context as dc


class FakeFiles:
    def __init__(self, records):
        self.records = records

    async def get_file_by_id(self, file_id):
        return self.records.get(file_id)


def record(owner, chars):
    return SimpleNamespace(user_id=owner, data={'content': 'x' * chars})


USER = SimpleNamespace(id='u1', role='user')


class PlanDocumentContext(unittest.TestCase):
    def plan(self, metadata, records, max_chars=1000):
        with mock.patch.object(dc, 'Files', FakeFiles(records)):
            return asyncio.run(dc.plan_document_context(metadata, USER, max_chars=max_chars))

    def test_files_within_cap_are_marked_full_and_described(self):
        items = [{'type': 'file', 'id': 'a', 'name': 'a.pdf'}, {'type': 'file', 'id': 'b', 'name': 'b.pdf'}]
        metadata = {'files': items}
        plan = self.plan(metadata, {'a': record('u1', 400), 'b': record('u1', 500)})
        self.assertEqual(plan['mode'], 'full')
        self.assertEqual([item['context'] for item in metadata['files']], ['full', 'full'])
        self.assertIn('a.pdf (400 characters)', dc.system_note(plan))
        self.assertTrue(dc.status_text(plan).startswith('Butun hujjat'))

    def test_over_cap_keeps_retrieval_and_says_excerpts(self):
        metadata = {'files': [{'type': 'file', 'id': 'a', 'name': 'big.pdf'}]}
        plan = self.plan(metadata, {'a': record('u1', 5000)})
        self.assertEqual(plan['mode'], 'excerpts')
        self.assertNotIn('context', metadata['files'][0])
        self.assertIn('Only retrieved excerpts', dc.system_note(plan))

    def test_user_choice_unreadable_and_foreign_files_are_left_alone(self):
        metadata = {
            'files': [
                {'type': 'file', 'id': 'a', 'name': 'a.pdf', 'context': 'full'},  # user toggled already
                {'type': 'file', 'id': 'x', 'name': 'x.pdf'},  # not in database
                {'type': 'file', 'id': 'https://example.org/p', 'name': 'web'},
            ]
        }
        self.assertIsNone(self.plan(metadata, {'a': record('u1', 10)}))
        self.assertIsNone(self.plan({'files': []}, {}))

    def test_other_users_file_without_grant_is_skipped(self):
        metadata = {'files': [{'type': 'file', 'id': 'a', 'name': 'a.pdf'}]}
        with mock.patch.object(dc, 'has_access_to_file', mock.AsyncMock(return_value=False)):
            self.assertIsNone(self.plan(metadata, {'a': record('someone-else', 10)}))

    def test_apply_adds_system_note_and_status(self):
        metadata = {'files': [{'type': 'file', 'id': 'a', 'name': 'a.pdf'}]}
        form = {'messages': [{'role': 'system', 'content': 'base'}, {'role': 'user', 'content': 'summarize'}]}
        events = []

        async def emitter(event):
            events.append(event)

        with mock.patch.object(dc, 'Files', FakeFiles({'a': record('u1', 10)})):
            plan = asyncio.run(dc.apply_document_context(form, metadata, USER, emitter))
        self.assertEqual(plan['mode'], 'full')
        self.assertIn('supplied IN FULL', form['messages'][0]['content'])
        self.assertTrue(form['messages'][0]['content'].startswith('base'))
        self.assertEqual(events[0]['type'], 'status')


class FastPathDocuments(unittest.TestCase):
    """Documents the legal specialist may read in one turn; None hands the turn to the model."""

    def docs(self, metadata, records, max_chars=1000):
        with mock.patch.object(dc, 'Files', FakeFiles(records)):
            return asyncio.run(dc.fast_path_documents(metadata, USER, max_chars=max_chars))

    def test_readable_files_within_the_cap_travel_with_their_names(self):
        metadata = {'files': [{'type': 'file', 'id': 'a', 'name': 'a.pdf'}, {'id': 'b', 'name': 'b.pdf'}]}
        docs = self.docs(metadata, {'a': record('u1', 400), 'b': record('u1', 500)})
        self.assertEqual([(d['name'], len(d['text'])) for d in docs], [('a.pdf', 400), ('b.pdf', 500)])

    def test_over_cap_unreadable_empty_and_non_file_items_keep_the_model(self):
        self.assertIsNone(self.docs({'files': [{'type': 'file', 'id': 'a', 'name': 'a'}]}, {'a': record('u1', 1001)}))
        self.assertIsNone(self.docs({'files': [{'type': 'file', 'id': 'x', 'name': 'x'}]}, {}))
        self.assertIsNone(self.docs({'files': [{'type': 'file', 'id': 'a', 'name': 'a'}]}, {'a': record('u1', 0)}))
        self.assertIsNone(self.docs({'files': [{'type': 'collection', 'id': 'k', 'name': 'kb'}]}, {}))
        self.assertIsNone(self.docs({'files': [{'type': 'file', 'id': 'https://example.org/p'}]}, {}))
        self.assertIsNone(self.docs({'files': []}, {}))
        self.assertIsNone(self.docs({}, {}))

    def test_a_file_of_another_user_without_grant_keeps_the_model(self):
        metadata = {'files': [{'type': 'file', 'id': 'a', 'name': 'a.pdf'}]}
        with mock.patch.object(dc, 'has_access_to_file', mock.AsyncMock(return_value=False)):
            self.assertIsNone(self.docs(metadata, {'a': record('someone-else', 10)}))


if __name__ == '__main__':
    unittest.main()
