"""
title: Prokuratura AI document generation
description: Create private downloadable Word, PDF and Excel files from supplied content.
version: 1.1.0
"""

import json


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
        return await self._generate({'format': format, 'title': title, 'content': content}, __user__)

    async def create_spreadsheet(self, title: str, sheets: list[dict], __user__: dict = None) -> str:
        """Create a real downloadable Excel (.xlsx) workbook from supplied data.
        Use only when the user requests a file. No formulas, macros or external data connections.
        :param title: Workbook title and filename (up to 160 characters).
        Max 20 columns/sheet, 1000 rows/sheet, 10000 cells total. Rows must match the column count.
        Cells are text, numbers, booleans or null; formulas are stored as literal text.
        :param sheets: 1-5 objects: {"name":"Sheet1","columns":["Name","Count"],"rows":[["Example",2]]}.
        """
        return await self._generate({'format': 'xlsx', 'title': title, 'sheets': sheets}, __user__)

    async def _generate(self, payload, user):
        from fastapi import HTTPException
        from open_webui.routers.generated_files import generate_file

        try:
            result = await generate_file(payload, user)
            return json.dumps(
                {
                    **result,
                    'instruction': (
                        'Return a Markdown download link using this exact URL and filename. '
                        'Explain in the user’s language that the download expires in 30 days. '
                        'Do not claim additional files were created.'
                    ),
                },
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
