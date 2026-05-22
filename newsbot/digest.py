"""Двухступенчатый конвейер: DeepSeek суммирует, Hermes редактирует дайджест."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Topic
from .llm import ChatClient
from .sources import Headline, format_for_prompt

_SUMMARIZER_SYSTEM = (
    "Ты — редактор новостной ленты. Тебе дают свежие заголовки и краткие "
    "описания по одной теме. Сделай выжимку строго по фактам из "
    "предоставленных материалов, без выдумок и без воды. По умолчанию 3–5 "
    "пунктов, но если в указании задано другое количество — точно следуй ему. "
    "Каждый пункт на русском языке — одно ёмкое предложение, начинается с «•». "
    "Не добавляй вступлений и заголовков.\n"
    "Если у заголовка указана строка «Ссылка: URL», в конце соответствующего "
    "пункта добавь ссылку на источник в виде HTML-тега Telegram: "
    '<a href="URL">источник</a>, скопировав URL дословно из этой строки. '
    "Не придумывай и не изменяй ссылки; если ссылки у заголовка нет — не "
    "добавляй её."
)

_GREETER_SYSTEM = (
    "Ты — ведущий тёплой утренней рассылки. Верни РОВНО две строки на русском "
    "без Markdown и без кавычек: первая — короткое приветствие с датой; вторая "
    "— короткое доброе пожелание дня. Допускается по одному эмодзи в строке. "
    "Никаких других строк и пояснений."
)

_LINK_RE = re.compile(r"""<a\s+href=(["'])(.*?)\1[^>]*>(.*?)</a>""", re.DOTALL | re.IGNORECASE)


@dataclass
class Section:
    title: str
    bullets: str  # готовые пункты от DeepSeek


def summarize_topic(
    deepseek: ChatClient, topic: Topic, headlines: list[Headline]
) -> Section | None:
    if not headlines:
        print(f"[digest] нет свежих новостей по теме «{topic.title}»")
        return None
    user = f"Тема: {topic.title}\n"
    if topic.focus:
        user += f"Указание: {topic.focus}\n"
    user += "\nЗаголовки:\n" + format_for_prompt(headlines)
    bullets = deepseek.complete(_SUMMARIZER_SYSTEM, user, temperature=0.3, max_tokens=500)
    return Section(title=topic.title, bullets=bullets.strip())


def sanitize_links(text: str, allowed: set[str]) -> str:
    """Оставляет только ссылки из набора allowed; чужие/выдуманные — разворачивает в текст."""

    def repl(m: re.Match[str]) -> str:
        url = m.group(2).strip()
        inner = m.group(3)
        if url in allowed:
            return f'<a href="{url}">{inner}</a>'
        return inner  # ссылки нет в списке источников — убираем тег, текст оставляем

    return _LINK_RE.sub(repl, text)


# Теги, которые Telegram разрешает в режиме HTML и которые мы сами расставляем.
_SAFE_TAG_RE = re.compile(r'</?[bi]>|<a href="[^"]*">|</a>', re.IGNORECASE)
_HREF_RE = re.compile(r'<a href="([^"]*)">', re.IGNORECASE)


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def harden_html(text: str) -> str:
    """Делает текст валидным Telegram-HTML.

    Экранирует «голые» &, <, > в тексте и & внутри href, сохраняя наши теги
    (<b>, <i>, <a href>). Без этого Telegram отвечает 400, и сообщение уходит
    как plain-текст с «сырыми» тегами.
    """
    out: list[str] = []
    pos = 0
    for m in _SAFE_TAG_RE.finditer(text):
        out.append(_escape_text(text[pos : m.start()]))
        tag = m.group(0)
        href = _HREF_RE.match(tag)
        if href:
            safe = href.group(1).replace("&", "&amp;")
            tag = f'<a href="{safe}">'
        out.append(tag)
        pos = m.end()
    out.append(_escape_text(text[pos:]))
    return "".join(out)


_FLIGHT_LINE_SYSTEM = (
    "Ты сжимаешь пост авиа-канала в ОДНУ короткую строку на русском. Укажи "
    "маршрут (откуда → куда), цену в рублях (она есть в тексте) и одну деталь "
    "(даты или туда-обратно / в одну сторону). Без эмодзи-мусора, хэштегов и "
    "призывов подписаться. Не выдумывай данные. Верни только строку — без «•» "
    "и без ссылок."
)

_TOUR_LINE_SYSTEM = (
    "Ты сжимаешь пост тревел-канала о туре в ОДНУ короткую строку на русском "
    "для семейного дайджеста. ОБЯЗАТЕЛЬНО укажи: страну и город/курорт, отель "
    "и его звёздность (если есть), цену в рублях (она есть в тексте) и одну "
    "деталь (даты, питание / «всё включено», сколько ночей). Конкретно, без "
    "воды. Без эмодзи-мусора, хэштегов и призывов подписаться. Не выдумывай "
    "данные. Верни только строку — без «•» и без ссылок."
)

_VISA_LINE_SYSTEM = (
    "Сожми новость про визы и правила въезда в одну короткую строку на русском: "
    "какая страна и что именно изменилось (ввела/отменила визу, безвиз, срок "
    "пребывания). Только факт, без воды, без «•» и без ссылок."
)


def _deal_line(
    deepseek: ChatClient, post: Headline | None, label: str, system: str
) -> str | None:
    if post is None:
        return None
    text = deepseek.complete(system, post.title, temperature=0.3, max_tokens=200)
    text = text.strip().lstrip("•").strip()
    if not text:
        return None
    link = f' <a href="{post.link}">подробнее</a>' if post.link else ""
    return f"• {label}: {text}{link}"


def build_tourism_section(
    deepseek: ChatClient,
    title: str,
    visa: Headline | None,
    flight: Headline | None,
    tours: list[Headline],
) -> Section | None:
    """Туризм: новость про визы, авиабилет (из Москвы) и до трёх туров."""
    lines: list[str] = []

    if visa is not None:
        src = f"{visa.title}. {visa.summary}".strip()
        text = deepseek.complete(_VISA_LINE_SYSTEM, src, temperature=0.3, max_tokens=160)
        text = text.strip().lstrip("•").strip()
        if text:
            link = f' <a href="{visa.link}">источник</a>' if visa.link else ""
            lines.append(f"• Визы: {text}{link}")

    flight_line = _deal_line(deepseek, flight, "Авиабилет", _FLIGHT_LINE_SYSTEM)
    if flight_line:
        lines.append(flight_line)

    for tour in tours:
        tour_line = _deal_line(deepseek, tour, "Тур", _TOUR_LINE_SYSTEM)
        if tour_line:
            lines.append(tour_line)

    if not lines:
        print("[digest] раздел «Туризм»: нет данных ни по одной строке")
        return None
    return Section(title=title, bullets="\n".join(lines))


def _intro_outro(hermes: ChatClient, date_str: str) -> tuple[str, str]:
    """Тёплое приветствие и пожелание дня от Hermes (с надёжным запасным вариантом)."""
    default = (f"☀️ Доброе утро! Свежий дайджест на {date_str}", "Хорошего дня! 🙌")
    try:
        out = hermes.complete(
            _GREETER_SYSTEM, f"Дата: {date_str}", temperature=0.7, max_tokens=120
        ).strip()
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if len(lines) >= 2:
            return lines[0], lines[-1]
    except Exception as exc:  # noqa: BLE001 — приветствие необязательно
        print(f"[digest] приветствие Hermes недоступно ({exc})")
    return default


def compose_digest(hermes: ChatClient, date_str: str, sections: list[Section]) -> str:
    """Детерминированная сборка: каждый раздел гарантированно со своим заголовком.

    Структуру НЕ доверяем модели (она склонна склеивать разделы и терять
    ссылки) — Hermes отвечает только за приветствие и пожелание дня.
    """
    greeting, wish = _intro_outro(hermes, date_str)
    parts = [f"<b>{greeting}</b>", ""]
    for section in sections:
        parts.append(f"<b>{section.title}</b>")
        parts.append(section.bullets)
        parts.append("")
    parts.append(wish)
    return "\n".join(parts).strip()
