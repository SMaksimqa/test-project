"""Конфигурация бота: темы, ленты и переменные окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    title: str  # заголовок раздела с эмодзи для дайджеста
    feeds: tuple[str, ...]
    focus: str = ""  # доп. указание модели, на чём сделать акцент
    keywords: tuple[str, ...] = ()  # если задано — оставляем только подходящие заголовки


# Темы дайджеста и их RSS-источники (русскоязычные, без ключей API).
# Если лента недоступна, она пропускается, остальные продолжают работать.
TOPICS: tuple[Topic, ...] = (
    Topic(
        key="it",
        title="💻 IT и технологии",
        feeds=(
            "https://habr.com/ru/rss/articles/?fl=ru",
            "https://3dnews.ru/news/rss/",
        ),
    ),
    Topic(
        key="world",
        title="🌍 В мире",
        feeds=(
            "https://lenta.ru/rss/news",
            "https://tass.ru/rss/v2.xml",
        ),
    ),
    Topic(
        key="gadgets",
        title="📱 Гаджеты",
        feeds=(
            "https://3dnews.ru/mobile/rss/",
            "https://www.ixbt.com/export/news.rss",
        ),
        focus=(
            "Это лента про гаджеты. Подавай каждый пункт как живую новость, а "
            "не как карточку из магазина: сначала что произошло или что вышло "
            "и чем это интересно/необычно (главная фишка, цена, кто "
            "производитель), затем при необходимости одна деталь. Допускается "
            "лёгкая ирония. Избегай рекламного тона, маркетинговых клише и "
            "сухого перечисления характеристик."
        ),
    ),
    Topic(
        key="worldcup",
        title="⚽ ЧМ-2026",
        feeds=(
            "https://www.championat.com/rss/news/football/",
            "https://news.google.com/rss/search?q=%D1%87%D0%B5%D0%BC%D0%BF%D0%B8%D0%BE%D0%BD%D0%B0%D1%82%20%D0%BC%D0%B8%D1%80%D0%B0%20%D0%BF%D0%BE%20%D1%84%D1%83%D1%82%D0%B1%D0%BE%D0%BB%D1%83%202026&hl=ru&gl=RU&ceid=RU:ru",
            "https://news.google.com/rss/search?q=%D0%BC%D1%83%D0%BD%D0%B4%D0%B8%D0%B0%D0%BB%D1%8C%202026%20%D1%81%D0%B1%D0%BE%D1%80%D0%BD%D0%B0%D1%8F&hl=ru&gl=RU&ceid=RU:ru",
        ),
        focus=(
            "Это новости только о Чемпионате мира по футболу 2026 "
            "(США/Канада/Мексика): подготовка к турниру, отбор и стыковые "
            "матчи, составы и фавориты, расписание, города и стадионы, билеты. "
            "Не пиши про РПЛ и клубные чемпионаты."
        ),
        keywords=(
            # Падежные формы «чемпионат(а/е/у) мира» — substring-сопоставление
            # не учитывает склонения, поэтому перечисляем их явно.
            "чемпионат мира",
            "чемпионата мира",
            "чемпионате мира",
            "чемпионату мира",
            "первенство мира",
            "первенства мира",
            "мундиал",  # мундиаль/мундиаля/мундиале
            "чм-2026",
            "чм 2026",
            "world cup",
        ),
    ),
)


@dataclass(frozen=True)
class Config:
    telegram_token: str
    telegram_chat_id: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    hermes_api_key: str
    hermes_model: str
    hermes_base_url: str
    dry_run: bool


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задана обязательная переменная окружения: {name}")
    return value


def _optional(name: str, default: str) -> str:
    # Пустая строка (например, незаданная GitHub-переменная) → значение по умолчанию.
    value = os.environ.get(name, "").strip()
    return value or default


def load_config() -> Config:
    return Config(
        telegram_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
        deepseek_api_key=_required("DEEPSEEK_API_KEY"),
        deepseek_model=_optional("DEEPSEEK_MODEL", "deepseek-chat"),
        deepseek_base_url=_optional("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        hermes_api_key=_required("HERMES_API_KEY"),
        hermes_model=_optional("HERMES_MODEL", "nousresearch/hermes-3-llama-3.1-70b"),
        hermes_base_url=_optional("HERMES_BASE_URL", "https://openrouter.ai/api/v1"),
        dry_run=os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes"},
    )
