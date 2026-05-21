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
    ),
    Topic(
        key="worldcup",
        title="⚽ ЧМ-2026",
        feeds=(
            "https://www.championat.com/rss/news/football/",
            "https://www.sports.ru/stat/export/rss/news.xml",
        ),
        focus=(
            "Сфокусируйся на новостях о Чемпионате мира по футболу 2026 "
            "(FIFA World Cup 2026, США/Канада/Мексика): отбор, составы, "
            "расписание, фавориты. Если прямых новостей о ЧМ-2026 нет — "
            "выбери самые относящиеся к подготовке к турниру."
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
