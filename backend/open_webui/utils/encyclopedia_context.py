"""Server-side encyclopedia lookup for general-knowledge turns.

Free model tool choice called search_encyclopedia on only 4 of 8 factual questions
(probe 2026-09-09). When the route classifier says "wiki", the search runs here and
its article is attached as retrieved context (a docs file item), so the model
always answers from the encyclopedia with native citations, like web search.
"""

import json
import logging

log = logging.getLogger(__name__)

ENCYCLOPEDIA_TOOL = 'search_encyclopedia'
MAX_SNIPPET_DOCS = 6


def encyclopedia_docs(result: dict) -> list:
    """Article text first, then result snippets, as RAG docs with source metadata."""
    docs, seen = [], set()
    articles = result.get('articles') or ([result['article']] if result.get('article') else [])
    for article in articles:
        if article.get('text') and article.get('url') and article['url'] not in seen:
            seen.add(article['url'])
            docs.append(
                {
                    'content': article['text'],
                    'metadata': {'source': article['url'], 'name': article.get('title') or article['url']},
                }
            )
    for hit in (result.get('results') or [])[:MAX_SNIPPET_DOCS]:
        url, snippet = hit.get('url'), (hit.get('snippet') or '').strip()
        if url and snippet and url not in seen:
            seen.add(url)
            docs.append({'content': snippet, 'metadata': {'source': url, 'name': hit.get('title') or url}})
    return docs


async def attach_encyclopedia_context(form_data: dict, tools_dict: dict, question: str) -> bool:
    """Run the bound encyclopedia tool for `question`; attach its docs to form_data['files']."""
    tool = (tools_dict or {}).get(ENCYCLOPEDIA_TOOL) or {}
    callable_ = tool.get('callable')
    if not callable_:
        return False
    try:
        raw = await callable_(query=question[:200])
        result = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as exc:  # noqa: BLE001 - the model still answers, without context
        log.warning('Encyclopedia context failed: %s', type(exc).__name__)
        return False
    if not isinstance(result, dict) or result.get('error'):
        return False
    docs = encyclopedia_docs(result)
    if not docs:
        log.info('Encyclopedia context: no article for the question; model answers unaided')
        return False
    log.info('Encyclopedia context: attached %d doc(s)', len(docs))
    files = list(form_data.get('files') or [])
    files.append(
        {
            'type': 'web_search',  # docs items bypass embedding and become cited sources
            'name': question[:200],
            'docs': docs,
            'urls': [doc['metadata']['source'] for doc in docs],
        }
    )
    form_data['files'] = files
    return True
