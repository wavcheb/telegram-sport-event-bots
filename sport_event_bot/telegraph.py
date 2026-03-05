# -*- coding: utf-8 -*-
"""Telegraph API helper for publishing payment logs as public pages."""

import asyncio
import datetime
import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

TELEGRAPH_API = 'https://api.telegra.ph'
_TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'telegraph_token.txt')
_token_cache: Optional[str] = None


def _api_call(method: str, **params) -> dict:
    url = f'{TELEGRAPH_API}/{method}'
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    if not result.get('ok'):
        raise RuntimeError(f"Telegraph API error: {result.get('error')}")
    return result['result']


def _get_token() -> str:
    global _token_cache
    if _token_cache:
        return _token_cache
    if os.path.exists(_TOKEN_FILE):
        with open(_TOKEN_FILE) as f:
            token = f.read().strip()
        if token:
            _token_cache = token
            return token
    result = _api_call('createAccount', short_name='SportBot', author_name='Sport Event Bot')
    _token_cache = result['access_token']
    with open(_TOKEN_FILE, 'w') as f:
        f.write(_token_cache)
    return _token_cache


def _build_content(event_title: str, entries: List[Tuple]) -> str:
    """Build Telegraph page content JSON from payment log entries."""
    nodes = [
        {'tag': 'p', 'children': [{'tag': 'b', 'children': [f'Событие: {event_title}']}]},
        {'tag': 'br'},
    ]
    if not entries:
        nodes.append({'tag': 'p', 'children': ['Оплат ещё нет.']})
    else:
        items = []
        for name, paid_at, for_friend in entries:
            if hasattr(paid_at, 'strftime'):
                time_str = paid_at.strftime('%H:%M')
            else:
                time_str = str(paid_at)[:5]
            note = 'скорее всего за друга' if for_friend else 'скорее всего за себя'
            items.append({'tag': 'li', 'children': [f'{name} — {time_str} ({note})']})
        nodes.append({'tag': 'ul', 'children': items})
    nodes.append({'tag': 'br'})
    nodes.append({
        'tag': 'p',
        'children': [f'Обновлено: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}']
    })
    return json.dumps(nodes, ensure_ascii=False)


def publish_payment_log_sync(event_title: str, entries: List[Tuple],
                              existing_url: Optional[str]) -> str:
    """Create or update a Telegraph page. Returns the page URL."""
    token = _get_token()
    content = _build_content(event_title, entries)
    title = f'Оплаты: {event_title}'
    if len(title) > 256:
        title = title[:253] + '...'

    if existing_url:
        path = existing_url.removeprefix('https://telegra.ph/')
        try:
            result = _api_call('editPage', access_token=token, path=path,
                               title=title, content=content)
            return result['url']
        except Exception:
            pass  # Page may be gone — fall through to create new

    result = _api_call('createPage', access_token=token,
                       title=title, content=content, author_name='Sport Event Bot')
    return result['url']


async def publish_payment_log(event_title: str, entries: List[Tuple],
                               existing_url: Optional[str]) -> str:
    """Async wrapper for publish_payment_log_sync."""
    return await asyncio.to_thread(publish_payment_log_sync, event_title, entries, existing_url)
