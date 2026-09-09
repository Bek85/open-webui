"""
title: Prokuratura AI document generation
description: Create private downloadable Word, PDF and Excel files from supplied content.
version: 1.0.0
"""

import json


class Tools:
    async def create_document(self, format: str, title: str, content: str, __user__: dict = None) -> str:
        """Create a real downloadable Word (docx) or PDF document from supplied Markdown.
        Use only when the user requests a file. Write the COMPLETE document content, not instructions to a writer.
        Supports headings, paragraphs, basic emphasis, source links and small Markdown tables.
        Does not research facts or read attachments. Preserve verified sources and the user's language/script.
        :param format: docx or pdf.
        :param title: Document title; also used as the filename (up to 160 characters).
        :param content: Complete Markdown content, up to 60000 characters. No images, HTML or remote inputs.
        """
        if format not in ('docx', 'pdf'):
            return json.dumps({'error': 'unsupported_format', 'message': 'Choose docx or pdf.'})
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
