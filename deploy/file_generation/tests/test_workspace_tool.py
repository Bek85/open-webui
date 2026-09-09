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


if __name__ == '__main__':
    unittest.main()
