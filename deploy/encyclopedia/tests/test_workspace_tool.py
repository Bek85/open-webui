"""Offline tests for the encyclopedia tool helpers (no kiwix needed)."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'encyclopedia_tool', Path(__file__).resolve().parents[1] / 'workspace_tool.py'
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Search: samarqand</title>
<item><title>Samarqand</title>
<link>/wiki/content/wikipedia_uz_all_maxi_2026-07/Samarqand</link>
<description>...<b>Samarqand</b> — O‘zbekistonning qadimiy &amp; go‘zal shahri...</description></item>
<item><title>No path</title><link></link><description>x</description></item>
</channel></rss>"""


class Parsing(unittest.TestCase):
    def test_books_spec(self):
        self.assertEqual(
            tool.parse_books(' uz:wikipedia_uz_all_maxi_2026-07, ru:wikipedia_ru_all_nopic_2026-01 '),
            {'uz': 'wikipedia_uz_all_maxi_2026-07', 'ru': 'wikipedia_ru_all_nopic_2026-01'},
        )
        self.assertEqual(tool.parse_books(''), {})

    def test_search_xml_items(self):
        hits = tool.parse_search_xml(SEARCH_XML)
        self.assertEqual(
            hits,
            [
                {
                    'title': 'Samarqand',
                    'path': 'Samarqand',
                    'snippet': '...Samarqand — O‘zbekistonning qadimiy & go‘zal shahri...',
                }
            ],
        )
        self.assertEqual(tool.parse_search_xml('<error>Invalid request</error>'), [])
        self.assertEqual(tool.parse_search_xml('not xml'), [])

    def test_html_to_text_strips_chrome_and_limits(self):
        page = (
            '<html><head><style>x{}</style></head><body><h1>Toshkent</h1><script>1</script>'
            '<p>Poytaxt<sup>[1]</sup>.</p><table><tr><td>t</td></tr></table></body></html>'
        )
        self.assertEqual(tool.html_to_text(page, 100), 'Toshkent\nPoytaxt .')
        self.assertTrue(tool.html_to_text('<p>' + 'a' * 50 + '</p>', 10).endswith('…'))


class Ranking(unittest.TestCase):
    def test_exact_title_first_then_titles_then_fulltext_unique(self):
        suggestions = [
            {'title': 'Samarqand vokzali', 'path': 'Samarqand_vokzali', 'snippet': ''},
            {'title': 'Samarqand', 'path': 'Samarqand', 'snippet': ''},
        ]
        search = [
            {'title': 'Samarqand vokzali', 'path': 'Samarqand_vokzali', 'snippet': 's'},
            {'title': 'Registon', 'path': 'Registon', 'snippet': 'r'},
        ]
        merged = tool.merge_hits('samarqand', suggestions, search)
        self.assertEqual([h['path'] for h in merged], ['Samarqand', 'Samarqand_vokzali', 'Registon'])
        self.assertEqual(tool.merge_hits('x', [], []), [])


class SearchTerms(unittest.TestCase):
    def test_question_words_removed_in_three_scripts(self):
        self.assertEqual(tool.search_terms("Amir Temur kim bo'lgan?"), ['Amir', 'Temur'])
        self.assertEqual(tool.search_terms('Алишер Навоий қачон туғилган?'), ['Алишер', 'Навоий', 'туғилган'])
        self.assertEqual(tool.search_terms('Кто такой Юрий Гагарин?'), ['Юрий', 'Гагарин'])
        self.assertEqual(tool.search_terms('Samarqand shahri haqida qisqacha ma’lumot ber'), ['Samarqand', 'shahri'])

    def test_all_question_words_falls_back_to_original(self):
        self.assertEqual(tool.search_terms('nima?'), ['nima'])


class SuggestionAcceptance(unittest.TestCase):
    hits = [
        {'title': 'Шатунов, Юрий Васильевич', 'path': 'a', 'snippet': ''},
        {'title': 'Юрий Гагарин', 'path': 'b', 'snippet': ''},
    ]

    def test_single_word_prefix_of_a_longer_question_needs_every_term(self):
        self.assertEqual([h['path'] for h in tool.accept_suggestions(['Юрий', 'Гагарин'], 1, self.hits)], ['b'])

    def test_two_word_prefix_is_trusted(self):
        orol = [{'title': 'Orol Dengizi', 'path': 'o', 'snippet': ''}]
        self.assertEqual(tool.accept_suggestions(['Orol', 'dengizi', 'quriyapti'], 2, orol), orol)
        self.assertEqual(tool.accept_suggestions(['Fotosintez'], 1, orol), orol)

    def test_mentions_is_accent_and_case_insensitive(self):
        self.assertTrue(tool.mentions('ruscha: Ю́рий Алексе́евич Гага́рин', ['Юрий', 'Гагарин']))
        self.assertFalse(tool.mentions('Chery eQ7 avtomobili', ['инфляция']))
        self.assertFalse(tool.mentions('abc', ['ab']))


class LanguageChoice(unittest.TestCase):
    books = {'uz': 'u', 'ru': 'r'}

    def test_latin_and_uzbek_cyrillic_prefer_uzbek(self):
        self.assertEqual(tool.detect_language('Samarqand tarixi', self.books), ['uz', 'ru'])
        self.assertEqual(tool.detect_language('Тошкент шаҳри', self.books), ['uz', 'ru'])

    def test_plain_cyrillic_prefers_russian(self):
        self.assertEqual(tool.detect_language('Ташкент история', self.books), ['ru', 'uz'])

    def test_only_available_books(self):
        self.assertEqual(tool.detect_language('Ташкент', {'uz': 'u'}), ['uz'])


class Urls(unittest.TestCase):
    def test_public_url_encodes_path(self):
        t = tool.Tools()
        t.valves.PUBLIC_URL = 'https://ai.example/wiki'
        url = t._url({'book': 'b', 'path': "Toshkent_(shahar)/O'z"})
        self.assertEqual(url, 'https://ai.example/wiki/content/b/Toshkent_(shahar)/O%27z')


if __name__ == '__main__':
    unittest.main()
