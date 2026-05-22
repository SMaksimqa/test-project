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

_EDITOR_SYSTEM = (
    "Ты — ведущий утренней новостной рассылки в Telegram. На основе готовых "
    "тезисов по темам составь тёплый, живой и лаконичный утренний дайджест на "
    "русском языке.\n"
    "Структура:\n"
    "1) короткое приветствие с датой;\n"
    "2) разделы по темам — заголовок раздела оберни в <b>…</b>, под ним "
    "пункты с «•». ОБЯЗАТЕЛЬНО включи ВСЕ присланные разделы в том же "
    "порядке и с теми же заголовками и эмодзи; ничего не пропускай и не "
    "объединяй темы между собой;\n"
    "3) в конце короткое доброе пожелание дня.\n"
    "Используй только HTML-разметку Telegram (<b>, <i>, <a href=\"…\">); не "
    "используй Markdown и не используй символы &, < и > вне тегов. Сохраняй "
    'теги <a href="…">источник</a> дословно: не меняй URL и не удаляй ссылки, '
    "оставляй их в конце пунктов. Опирайся строго на присланные тезисы, ничего "
    "не выдумывай. Уложись примерно в 3500 символов."
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


_TOUR_LINE_SYSTEM = (
    "Ты сжимаешь рекламный пост тревел-канала в ОДНУ короткую строку на русском "
    "для семейного дайджеста. Укажи направление и цену в рублях, если она есть "
    "в тексте, плюс одну ключевую деталь (даты, звёзды отеля, «всё включено»). "
    "Без эмодзи-мусора, хэштегов и призывов подписаться. Не выдумывай цену, "
    "если её нет в тексте. Верни только строку — без «•» и без ссылок."
)

_VISA_LINE_SYSTEM = (
    "Сожми новость про визы и правила въезда в одну короткую строку на русском: "
    "какая страна и что именно изменилось (ввела/отменила визу, безвиз, срок "
    "пребывания). Только факт, без воды, без «•» и без ссылок."
)


def _deal_line(deepseek: ChatClient, post: Headline | None, label: str) -> str | None:
    if post is None:
        return None
    text = deepseek.complete(_TOUR_LINE_SYSTEM, post.title, temperature=0.3, max_tokens=160)
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
    tour: Headline | None,
) -> Section | None:
    """Туризм тремя строками: новость про визы, авиабилет, тур."""
    lines: list[str] = []

    if visa is not None:
        src = f"{visa.title}. {visa.summary}".strip()
        text = deepseek.complete(_VISA_LINE_SYSTEM, src, temperature=0.3, max_tokens=160)
        text = text.strip().lstrip("•").strip()
        if text:
            link = f' <a href="{visa.link}">источник</a>' if visa.link else ""
            lines.append(f"• Визы: {text}{link}")

    flight_line = _deal_line(deepseek, flight, "Авиабилет")
    if flight_line:
        lines.append(flight_line)

    tour_line = _deal_line(deepseek, tour, "Тур")
    if tour_line:
        lines.append(tour_line)

    if not lines:
        print("[digest] раздел «Туризм»: нет данных ни по одной строке")
        return None
    return Section(title=title, bullets="\n".join(lines))


def compose_digest(hermes: ChatClient, date_str: str, sections: list[Section]) -> str:
    blocks = "\n\n".join(f"{s.title}\n{s.bullets}" for s in sections)
    user = (
        f"Сегодня {date_str}. Составь утренний дайджест из этих тезисов, "
        f"сохрани порядок и заголовки разделов:\n\n{blocks}"
    )
    return hermes.complete(_EDITOR_SYSTEM, user, temperature=0.6, max_tokens=1600).strip()


def append_missing(message: str, sections: list[Section]) -> str:
    """Страховка: дописывает разделы, которые редактор пропустил.

    Присутствие раздела проверяем по его эмодзи (он уникален для темы и
    устойчив к тому, что модель переформулировала текст заголовка).
    """
    missing = [s for s in sections if (m := s.title.split()[0]) and m not in message]
    if not missing:
        return message
    extra = "\n\n".join(f"<b>{s.title}</b>\n{s.bullets}" for s in missing)
    return f"{message}\n\n{extra}"


def assemble_plain(date_str: str, sections: list[Section]) -> str:
    """Резервная сборка дайджеста, если редактор-модель недоступна."""
    parts = [f"<b>☀️ Доброе утро! Новости на {date_str}</b>", ""]
    for s in sections:
        parts.append(f"<b>{s.title}</b>")
        parts.append(s.bullets)
        parts.append("")
    parts.append("Хорошего дня! 🙌")
    return "\n".join(parts).strip()
