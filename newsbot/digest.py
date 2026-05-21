"""Двухступенчатый конвейер: DeepSeek суммирует, Hermes редактирует дайджест."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Topic
from .llm import ChatClient
from .sources import Headline, format_for_prompt

_SUMMARIZER_SYSTEM = (
    "Ты — редактор новостной ленты. Тебе дают свежие заголовки и краткие "
    "описания по одной теме. Сделай выжимку: 3–5 кратких пунктов на русском "
    "языке строго по фактам из предоставленных материалов, без выдумок и без "
    "воды. Каждый пункт — одно ёмкое предложение, начинается с «•». "
    "Не добавляй вступлений и заголовков."
)

_EDITOR_SYSTEM = (
    "Ты — ведущий утренней новостной рассылки в Telegram. На основе готовых "
    "тезисов по темам составь тёплый, живой и лаконичный утренний дайджест на "
    "русском языке.\n"
    "Структура:\n"
    "1) короткое приветствие с датой;\n"
    "2) разделы по темам — заголовок раздела оберни в <b>…</b>, под ним 3–5 "
    "пунктов с «•»;\n"
    "3) в конце короткое доброе пожелание дня.\n"
    "Используй только HTML-разметку Telegram (<b>, <i>); не используй Markdown "
    "и не используй символы &, < и > вне тегов. Опирайся строго на присланные "
    "тезисы, ничего не выдумывай. Уложись примерно в 3500 символов."
)


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


def compose_digest(hermes: ChatClient, date_str: str, sections: list[Section]) -> str:
    blocks = "\n\n".join(f"{s.title}\n{s.bullets}" for s in sections)
    user = (
        f"Сегодня {date_str}. Составь утренний дайджест из этих тезисов, "
        f"сохрани порядок и заголовки разделов:\n\n{blocks}"
    )
    return hermes.complete(_EDITOR_SYSTEM, user, temperature=0.6, max_tokens=1600).strip()


def assemble_plain(date_str: str, sections: list[Section]) -> str:
    """Резервная сборка дайджеста, если редактор-модель недоступна."""
    parts = [f"<b>☀️ Доброе утро! Новости на {date_str}</b>", ""]
    for s in sections:
        parts.append(f"<b>{s.title}</b>")
        parts.append(s.bullets)
        parts.append("")
    parts.append("Хорошего дня! 🙌")
    return "\n".join(parts).strip()
