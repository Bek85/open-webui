"""Explicit source contract for opt-in native Workspace Tools."""

from urllib.parse import urlsplit


def native_tool_sources(result: dict) -> list[dict]:
    """Accept bounded HTTP(S) citations, never arbitrary source/UI metadata."""
    citations = result.get('citations')
    if not isinstance(citations, list) or result.get('error'):
        return []
    sources, seen = [], set()
    for item in citations[:64]:
        if not isinstance(item, dict):
            continue
        url = item.get('url')
        if not isinstance(url, str) or len(url) > 4096:
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or url in seen:
            continue
        seen.add(url)
        title = str(item.get('title') or url)[:512]
        content = str(item.get('content') or title)[:12000]
        sources.append(
            {
                'source': {'id': url, 'name': title, 'type': 'web'},
                'document': [content],
                'metadata': [{'source': url, 'url': url, 'name': title}],
            }
        )
    return sources
