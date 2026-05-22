"""Отправка сообщений в Telegram через Bot API."""

from __future__ import annotations

import html
import re

import requests

_API = "https://api.telegram.org/bot{token}/sendMessage"
_LIMIT = 4000  # запас к лимиту Telegram в 4096 символов
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    """Чистый текст без HTML — на случай, если разметку не удалось отправить."""
    return html.unescape(_TAG_RE.sub("", text))


def _split(text: str, limit: int = _LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit and current:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def send_message(token: str, chat_id: str, text: str, timeout: int = 30) -> None:
    url = _API.format(token=token)
    for chunk in _split(text):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 400:
            # Невалидный HTML — отправляем уже без тегов, чистым текстом.
            print(f"[telegram] 400 с HTML, повтор без разметки: {resp.text[:200]}")
            payload.pop("parse_mode")
            payload["text"] = _strip_tags(chunk)
            resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
