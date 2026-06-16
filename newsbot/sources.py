"""Получение свежих заголовков из RSS/Atom-лент (только стандартная библиотека + requests)."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
    published: float | None = None  # epoch-время публикации для сортировки по свежести


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


_GNEWS_RE = re.compile(r"^https?://news\.google\.com/(?:rss/)?articles/([A-Za-z0-9_\-]+)")


def _direct_link(url: str) -> str:
    """Пытается достать прямую ссылку из редирект-ссылки Google News.

    Старый формат хранит исходный URL внутри base64 как protobuf-поле с длиной —
    читаем его (без сети). Новый формат URL не содержит — оставляем как есть.
    """
    m = _GNEWS_RE.match(url)
    if not m:
        return url
    blob = m.group(1)
    try:
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    except Exception:  # noqa: BLE001
        return url

    i, n = 0, len(raw)
    while i < n:
        if raw[i] != 0x22:  # ищем поле 4 (length-delimited) — там лежит URL
            i += 1
            continue
        i += 1
        length = shift = 0
        while i < n:  # varint-длина
            b = raw[i]
            i += 1
            length |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        candidate = raw[i : i + length]
        i += length
        try:
            text = candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text.startswith("http") and "news.google.com" not in text and len(text) >= 12:
            return text
    return url


def _link(item: ET.Element) -> str:
    el = _find(item, "link")
    if el is None:
        return ""
    # RSS: текст элемента; Atom: атрибут href.
    return _direct_link((el.text or el.get("href") or "").strip())


def _published(item: ET.Element) -> float | None:
    el = _find(item, "pubdate", "published", "updated", "date")
    if el is None or not el.text:
        return None
    raw = el.text.strip()
    try:
        return parsedate_to_datetime(raw).timestamp()  # RSS (RFC 822)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()  # Atom (ISO)
        except ValueError:
            return None


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
        items.append(
            Headline(title=title, summary=summary, link=_link(el), published=_published(el))
        )
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
    # Свежие — вперёд: так дайджест каждый день берёт новые новости, а не одни и те же.
    result.sort(key=lambda h: h.published or 0.0, reverse=True)
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


_PRICE_RE = re.compile(
    r"(\d[\d\s., ]{0,12}\d|\d)\s*(?:₽|руб|р\.|rub)", re.IGNORECASE
)


def has_price(text: str) -> bool:
    """Есть ли в тексте цена в рублях (₽/руб/р.)."""
    return _PRICE_RE.search(text or "") is not None


def min_price_rub(text: str) -> int | None:
    """Минимальная рублёвая цена из текста (для выбора самого дешёвого тура)."""
    values: list[int] = []
    for match in _PRICE_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1))
        if not digits:
            continue
        value = int(digits)
        if 1000 <= value <= 5_000_000:  # отсекаем мусор: годы, мелкие числа
            values.append(value)
    return min(values) if values else None


def format_for_prompt(headlines: list[Headline]) -> str:
    lines = []
    for i, h in enumerate(headlines, 1):
        line = f"{i}. {h.title}"
        if h.summary:
            line += f" — {h.summary}"
        lines.append(line)
    return "\n".join(lines)


class _TgPreviewParser(HTMLParser):
    """Достаёт текст и ссылки постов из веб-предпросмотра t.me/s/<канал>."""

    def __init__(self) -> None:
        super().__init__()
        self.posts: list[tuple[str, str]] = []  # (текст, ссылка)
        self._post_url = ""
        self._buy_url = ""
        self._in_text = False
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        cls = d.get("class", "")
        if tag == "div" and "data-post" in d:
            self._flush()
            self._post_url = f"https://t.me/{d['data-post']}"
            self._buy_url = ""
        if tag == "div" and "tgme_widget_message_text" in cls:
            self._in_text = True
            self._depth = 1
            self._parts = []
            return
        if not self._in_text:
            return
        self._depth += 1
        if tag == "br":
            self._parts.append(" ")
        if tag == "a":
            href = d.get("href", "")
            if href.startswith("http") and "t.me/" not in href and not self._buy_url:
                self._buy_url = href

    def handle_endtag(self, tag: str) -> None:
        if self._in_text and tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in_text = False

    def handle_data(self, data: str) -> None:
        if self._in_text:
            self._parts.append(data)

    def _flush(self) -> None:
        text = _clean("".join(self._parts), limit=400)
        if self._post_url and text:
            self.posts.append((text, self._buy_url or self._post_url))
        self._parts = []
        self._post_url = ""

    def close(self) -> None:  # noqa: D401
        super().close()
        self._flush()


def fetch_telegram_channel(channel: str, limit: int = 5) -> list[Headline]:
    """Свежие посты публичного канала через t.me/s/<канал> (новые — первыми)."""
    url = f"https://t.me/s/{channel}"
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
        resp.raise_for_status()
        parser = _TgPreviewParser()
        parser.feed(resp.text)
        parser.close()
    except Exception as exc:  # noqa: BLE001 — недоступный канал не должен ронять бот
        print(f"[sources] канал недоступен t.me/s/{channel}: {exc}")
        return []
    posts = parser.posts[-limit:][::-1]  # предпросмотр идёт от старых к новым
    return [Headline(title=text, summary="", link=link) for text, link in posts]


@dataclass(frozen=True)
class ChannelPost:
    """Пост канала с инфой об охвате — для сортировки «топ за день»."""

    text: str
    link: str
    published: float  # epoch UTC, 0 если дату не разобрали
    reactions: int  # сумма всех реакций
    views: int  # количество просмотров


_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([KkMmКкМм])?")
# Самозакрывающиеся теги (HTMLParser не вызывает для них endtag) — не качаем глубину.
_VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}


def _parse_short_number(text: str) -> int:
    """Парсит «15.2K», «1,5M», «42» в целое число (Telegram даёт сокращения)."""
    m = _NUM_RE.search(text or "")
    if not m:
        return 0
    value = float(m.group(1).replace(",", "."))
    suffix = (m.group(2) or "").lower()
    if suffix in ("k", "к"):
        value *= 1_000
    elif suffix in ("m", "м"):
        value *= 1_000_000
    return int(value)


class _TgEngagementParser(HTMLParser):
    """Парсит t.me/s/<канал>: текст, ссылку, время, реакции и просмотры поста."""

    def __init__(self) -> None:
        super().__init__()
        self.posts: list[ChannelPost] = []
        self._reset_current()

    def _reset_current(self) -> None:
        self._post_id = ""
        self._text_parts: list[str] = []
        self._views_text = ""
        self._datetime = ""
        self._reactions = 0
        self._in_text = 0
        self._in_views = 0
        self._in_reaction_value = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        cls = d.get("class", "")
        if d.get("data-post"):
            self._flush()
            self._post_id = d["data-post"]
            return
        if not self._post_id:
            return
        void = tag in _VOID_TAGS
        if "tgme_widget_message_text" in cls:
            self._in_text = 1
            return
        if self._in_text:
            if tag == "br":
                self._text_parts.append(" ")
            if not void:
                self._in_text += 1
        if "tgme_widget_message_views" in cls:
            self._in_views = 1
        elif self._in_views and not void:
            self._in_views += 1
        if "tgme_reaction_value" in cls:
            self._in_reaction_value = 1
        elif self._in_reaction_value and not void:
            self._in_reaction_value += 1
        if tag == "time" and d.get("datetime") and not self._datetime:
            self._datetime = d["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if not self._post_id:
            return
        if self._in_text:
            self._in_text -= 1
        if self._in_views:
            self._in_views -= 1
        if self._in_reaction_value:
            self._in_reaction_value -= 1

    def handle_data(self, data: str) -> None:
        if not self._post_id:
            return
        if self._in_text:
            self._text_parts.append(data)
        if self._in_views:
            self._views_text += data
        if self._in_reaction_value:
            self._reactions += _parse_short_number(data)

    def _flush(self) -> None:
        if not self._post_id:
            return
        text = _clean("".join(self._text_parts), limit=400)
        ts = 0.0
        if self._datetime:
            try:
                ts = datetime.fromisoformat(
                    self._datetime.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                ts = 0.0
        if text:
            self.posts.append(
                ChannelPost(
                    text=text,
                    link=f"https://t.me/{self._post_id}",
                    published=ts,
                    reactions=self._reactions,
                    views=_parse_short_number(self._views_text),
                )
            )
        self._reset_current()

    def close(self) -> None:  # noqa: D401
        super().close()
        self._flush()


def fetch_telegram_top(
    channel: str, hours: int = 24, limit: int = 5
) -> list[ChannelPost]:
    """Топ постов канала за последние N часов — по реакциям, потом по просмотрам.

    Если канал не отдаёт реакций (отключены), фактически сортируется по
    просмотрам — это разумный прокси для «залайканных» постов.
    """
    url = f"https://t.me/s/{channel}"
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
        resp.raise_for_status()
        parser = _TgEngagementParser()
        parser.feed(resp.text)
        parser.close()
    except Exception as exc:  # noqa: BLE001 — недоступный канал не должен ронять бот
        print(f"[sources] канал недоступен t.me/s/{channel}: {exc}")
        return []
    cutoff = datetime.now().timestamp() - hours * 3600
    fresh = [p for p in parser.posts if p.published >= cutoff]
    fresh.sort(key=lambda p: (p.reactions, p.views), reverse=True)
    return fresh[:limit]
