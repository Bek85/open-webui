import unittest

from open_webui.utils.tool_citations import native_tool_sources


class CitationTests(unittest.TestCase):
    def test_valid_citation_and_duplicates(self):
        item = {'url': 'https://lex.uz/docs/1', 'title': 'Law', 'content': 'Article text'}
        result = native_tool_sources({'citations': [item, item]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['metadata'][0]['source'], item['url'])
        self.assertEqual(result[0]['document'], ['Article text'])

    def test_malformed_and_unsafe_sources(self):
        for value in (
            None,
            'bad',
            [{'url': 'javascript:alert(1)'}],
            [{'url': 'https://'}],
            [None],
            [{'url': 'http://['}],
        ):
            self.assertEqual(native_tool_sources({'citations': value}), [])
        self.assertEqual(native_tool_sources({'error': 'denied', 'citations': [{'url': 'https://lex.uz/1'}]}), [])

    def test_limits(self):
        result = native_tool_sources(
            {'citations': [{'url': f'https://lex.uz/{i}', 'content': 'a' * 13000} for i in range(80)]}
        )
        self.assertEqual(len(result), 64)
        self.assertEqual(len(result[0]['document'][0]), 12000)


if __name__ == '__main__':
    unittest.main()
