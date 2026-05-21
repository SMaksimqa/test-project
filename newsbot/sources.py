"""Получение свежих заголовков из RSS/Atom-лент (только стандартная библиотека + requests)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import requests

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_UA = "Mozilla/5.0 (compatible; MorningNewsBot/1.0; +https://github.com/morning-news-bot)"


@dataclass(frozen=True)
class Headline:
    title: str
    summary: str
    link: str


def _clean(text: str, limit: int = 280) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit].rstrip() if len(text) > limit else text


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find(item: ET.Element, *names: str) -> ET.Element | None:
    wanted = set(names)
    for child in item:
        if _local(child.tag) in wanted:
            return child
    return None


def _link(item: ET.Element) -> str:
    el = _find(item, "link")
    if el is None:
        return ""
    # RSS: текст элемента; Atom: атрибут href.
    return (el.text or el.get("href") or "").strip()


def _parse(content: bytes) -> list[Headline]:
    root = ET.fromstring(content)
    items: list[Headline] = []
    for el in root.iter():
        if _local(el.tag) not in {"item", "entry"}:
            continue
        title_el = _find(el, "title")
        title = _clean(title_el.text if title_el is not None else "", limit=200)
        if not title:
            continue
        summary_el = _find(el, "description", "summary", "content")
        summary = _clean(summary_el.text if summary_el is not None else "")
        items.append(Headline(title=title, summary=summary, link=_link(el)))
    return items


def fetch_headlines(feeds: tuple[str, ...], per_feed: int = 8) -> list[Headline]:
    """Собирает заголовки из всех лент темы, пропуская недоступные."""
    seen: set[str] = set()
    result: list[Headline] = []
    for url in feeds:
        try:
            resp = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
            resp.raise_for_status()
            parsed = _parse(resp.content)
        except Exception as exc:  # noqa: BLE001 — одна лента не должна ронять бот
            print(f"[sources] лента недоступна {url}: {exc}")
            continue
        for h in parsed[:per_feed]:
            key = h.title.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(h)
    return result


def filter_by_keywords(
    headlines: list[Headline], keywords: tuple[str, ...]
) -> list[Headline]:
    """Оставляет только заголовки, где встречается хотя бы одно ключевое слово."""
    if not keywords:
        return headlines
    kws = [k.lower() for k in keywords]
    out = []
    for h in headlines:
        text = f"{h.title} {h.summary}".lower()
        if any(k in text for k in kws):
            out.append(h)
    return out


def format_for_prompt(headlines: list[Headline]) -> str:
    lines = []
    for i, h in enumerate(headlines, 1):
        line = f"{i}. {h.title}"
        if h.summary:
            line += f" — {h.summary}"
        lines.append(line)
    return "\n".join(lines)
