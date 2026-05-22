"""Сборка дайджеста: общий код для крона (__main__) и слушателя (listen)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import digest, sources
from .config import TOPICS, Config
from .llm import ChatClient

MSK = timezone(timedelta(hours=3))  # Москва, UTC+3 без перехода на летнее время

_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _date_str(now: datetime) -> str:
    return f"{now.day} {_MONTHS[now.month - 1]} {now.year} г."


def make_clients(cfg: Config) -> tuple[ChatClient, ChatClient]:
    deepseek = ChatClient(
        api_key=cfg.deepseek_api_key,
        base_url=cfg.deepseek_base_url,
        model=cfg.deepseek_model,
    )
    hermes = ChatClient(
        api_key=cfg.hermes_api_key,
        base_url=cfg.hermes_base_url,
        model=cfg.hermes_model,
        extra_headers={
            "HTTP-Referer": "https://github.com/morning-news-bot",
            "X-Title": "Morning News Bot",
        },
    )
    return deepseek, hermes


def generate_digest(deepseek: ChatClient, hermes: ChatClient) -> str | None:
    """Собирает дайджест по всем темам. Возвращает готовый текст или None."""
    date_str = _date_str(datetime.now(MSK))
    print(f"[pipeline] сборка дайджеста, дата (МСК): {date_str}")

    sections: list[digest.Section] = []
    for topic in TOPICS:
        headlines = sources.fetch_headlines(topic.feeds)
        headlines = sources.filter_by_keywords(headlines, topic.keywords)
        print(f"[pipeline] тема «{topic.title}»: {len(headlines)} заголовков")
        section = digest.summarize_topic(deepseek, topic, headlines)
        if section:
            sections.append(section)

    if not sections:
        print("[pipeline] не удалось собрать ни одной новости")
        return None

    try:
        message = digest.compose_digest(hermes, date_str, sections)
    except Exception as exc:  # noqa: BLE001 — лучше отправить черновик, чем ничего
        print(f"[pipeline] редактор Hermes недоступен ({exc}), резервная сборка")
        message = digest.assemble_plain(date_str, sections)

    return digest.append_missing(message, sections)
