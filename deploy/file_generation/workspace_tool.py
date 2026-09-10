"""
title: Prokuratura AI document generation
description: Create private downloadable Word, PDF and Excel files from supplied content.
version: 1.2.0
"""

import json
import re

# Blocks the chat renders as pictures; the file renderer has no browser, so they would print as source text.
VISUAL_FENCE = re.compile(r'^[ \t]*```[ \t]*(mermaid|html|svg)\b.*?^[ \t]*```[ \t]*$\n?', re.M | re.S | re.I)


def previous_answer(messages) -> str:
    """Text of the most recent assistant turn; exporting it verbatim avoids regenerating thousands of tokens."""
    for message in reversed(messages or []):
        if message.get('role') != 'assistant':
            continue
        content = message.get('content')
        if isinstance(content, list):
            content = '\n'.join(
                part.get('text', '') for part in content if isinstance(part, dict) and part.get('type') == 'text'
            )
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ''


def strip_visual_blocks(content: str) -> tuple[str, int]:
    """Drop mermaid/html/svg fences and report how many were removed so the model can tell the user."""
    stripped, count = VISUAL_FENCE.subn('', content or '')
    return stripped.strip(), count


class Tools:
    async def create_document(
        self,
        format: str,
        title: str,
        content: str = '',
        use_previous_answer: bool = False,
        __user__: dict = None,
        __messages__: list = None,
    ) -> str:
        """Create a real downloadable Word (docx) or PDF document from Markdown.
        Use only when the user requests a file.
        If the user wants the previous answer (or "this information") as a file, set use_previous_answer=true and
        leave content EMPTY: the previous answer is exported verbatim, which is much faster than rewriting it.
        Only write content yourself for a NEW document; then supply the COMPLETE text, not instructions to a writer.
        Supports headings, paragraphs, basic emphasis, source links and small Markdown tables.
        Diagrams and visuals (mermaid, html, svg blocks) cannot be drawn into files and are omitted;
        the result reports how many were omitted so you can tell the user.
        Does not research facts or read attachments. Preserve verified sources and the user's language/script.
        :param format: docx or pdf.
        :param title: Document title; also used as the filename (up to 160 characters).
        :param content: Complete Markdown for a NEW document (max 60000 chars); empty if use_previous_answer is true.
        :param use_previous_answer: true to export the assistant's previous answer verbatim instead of writing content.
        """
        if format not in ('docx', 'pdf'):
            return json.dumps({'error': 'unsupported_format', 'message': 'Choose docx or pdf.'})
        if use_previous_answer or not (content or '').strip():
            content = previous_answer(__messages__)
            if not content:
                return json.dumps(
                    {'error': 'no_previous_answer', 'message': 'There is no previous answer to export; supply content.'}
                )
        content, omitted = strip_visual_blocks(content)
        if not content:
            return json.dumps(
                {
                    'error': 'only_visuals',
                    'message': 'The answer consists only of diagrams or visuals, which cannot be rendered into a file.',
                }
            )
        return await self._generate({'format': format, 'title': title, 'content': content}, __user__, omitted)

    async def create_spreadsheet(self, title: str, sheets: list[dict], __user__: dict = None) -> str:
        """Create a real downloadable Excel (.xlsx) workbook from supplied data.
        Use only when the user requests a file. No formulas, macros or external data connections.
        :param title: Workbook title and filename (up to 160 characters).
        Max 20 columns/sheet, 1000 rows/sheet, 10000 cells total. Rows must match the column count.
        Cells are text, numbers, booleans or null; formulas are stored as literal text.
        :param sheets: 1-5 objects: {"name":"Sheet1","columns":["Name","Count"],"rows":[["Example",2]]}.
        """
        return await self._generate({'format': 'xlsx', 'title': title, 'sheets': sheets}, __user__)

    async def _generate(self, payload, user, omitted_visuals: int = 0):
        from fastapi import HTTPException
        from open_webui.routers.generated_files import generate_file

        instruction = (
            'Return a Markdown download link using this exact URL and filename. '
            'Explain in the user’s language that the download expires in 30 days. '
            'Do not claim additional files were created.'
        )
        if omitted_visuals:
            instruction += (
                f' {omitted_visuals} diagram/visual block(s) shown in the chat were NOT included in the file '
                'because files cannot contain rendered diagrams; tell the user this in their language.'
            )
        try:
            result = await generate_file(payload, user)
            return json.dumps(
                {**result, 'omitted_visuals': omitted_visuals, 'instruction': instruction},
                ensure_ascii=False,
            )
        except HTTPException as exc:
            return json.dumps(
                {
                    'error': 'file_generation_failed',
                    'status': exc.status_code,
                    'instruction': (
                        'Explain in the user’s language that no file was created. '
                        'For 422 ask for a smaller or corrected document/table; '
                        'for 429 ask the user to try later. Never invent a download link.'
                    ),
                }
            )
