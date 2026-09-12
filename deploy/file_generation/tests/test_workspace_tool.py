"""Offline tests for the workspace tool helpers (no renderer needed)."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'workspace_tool', Path(__file__).resolve().parents[1] / 'workspace_tool.py'
)
workspace_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace_tool)


class PreviousAnswer(unittest.TestCase):
    def test_latest_assistant_text_wins_and_parts_are_joined(self):
        messages = [
            {'role': 'assistant', 'content': 'old'},
            {'role': 'user', 'content': 'pdf qilib ber'},
            {
                'role': 'assistant',
                'content': [{'type': 'text', 'text': ' # Sarlavha '}, {'type': 'image_url', 'image_url': {}}],
            },
            {'role': 'user', 'content': 'shu'},
        ]
        self.assertEqual(workspace_tool.previous_answer(messages), '# Sarlavha')

    def test_empty_history(self):
        self.assertEqual(workspace_tool.previous_answer([]), '')
        self.assertEqual(workspace_tool.previous_answer(None), '')
        self.assertEqual(workspace_tool.previous_answer([{'role': 'assistant', 'content': '  '}]), '')


class StripVisualBlocks(unittest.TestCase):
    def test_visual_fences_removed_and_counted(self):
        text = (
            '# Meros\n\nQuyida sxema:\n\n```mermaid\ngraph TD\n  A --> B\n```\n\nIzoh matni.\n'
            '```HTML\n<div>x</div>\n```\n\n```svg\n<svg/>\n```\n'
        )
        stripped, count = workspace_tool.strip_visual_blocks(text)
        self.assertEqual(count, 3)
        self.assertEqual(stripped, '# Meros\n\nQuyida sxema:\n\n\nIzoh matni.')
        self.assertNotIn('graph TD', stripped)

    def test_ordinary_code_and_prose_untouched(self):
        text = "Matn\n\n```python\nprint(1)\n```\n\nmermaid so'zi oddiy matnda."
        self.assertEqual(workspace_tool.strip_visual_blocks(text), (text, 0))
        self.assertEqual(workspace_tool.strip_visual_blocks(''), ('', 0))
        self.assertEqual(workspace_tool.strip_visual_blocks(None), ('', 0))

    def test_only_visuals_leaves_nothing(self):
        self.assertEqual(workspace_tool.strip_visual_blocks('```mermaid\ngraph LR\nA-->B\n```'), ('', 1))


class Failure(unittest.TestCase):
    def test_busy_and_quota_get_different_advice(self):
        busy = workspace_tool.failure(429, 'busy')
        quota = workspace_tool.failure(429, 'quota')
        self.assertEqual((busy['reason'], quota['reason']), ('busy', 'quota'))
        self.assertIn('try again in a moment', busy['instruction'])
        self.assertIn('store is full', quota['instruction'])
        self.assertNotIn('try again', quota['instruction'])

    def test_other_statuses(self):
        self.assertIn('smaller or corrected', workspace_tool.failure(422, 'x')['instruction'])
        unavailable = workspace_tool.failure(503, 'File generation unavailable')
        self.assertIsNone(unavailable['reason'])
        self.assertIn('unavailable', unavailable['instruction'])
        for result in (workspace_tool.failure(429, 'busy'), unavailable):
            self.assertEqual(result['error'], 'file_generation_failed')
            self.assertIn('Never invent a download link', result['instruction'])


if __name__ == '__main__':
    unittest.main()
