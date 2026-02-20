from __future__ import annotations

import hashlib
import re


def clip_text(text: str, *, max_chars: int = 3000) -> str:
    source = text or ''
    if len(source) <= max_chars:
        return source
    dropped = len(source) - max_chars
    return source[:max_chars] + f'\n...[truncated {dropped} chars]'


def text_signature(text: str, *, max_chars: int = 1000) -> str:
    payload = re.sub(r'\s+', ' ', str(text or '').strip().lower())
    if not payload:
        return ''
    if len(payload) > max_chars:
        payload = payload[:max_chars]
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
