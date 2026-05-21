"""Точка входа: собрать новости, составить дайджест и отправить в Telegram."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import digest, sources, telegram
from .config import TOPICS, load_config
from .llm import ChatClient

MSK = timezone(timedelta(hours=3))  # Москва, UTC+3 без перехода на летнее время

_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _date_str(now: datetime) -> str:
    return f"{now.day} {_MONTHS[now.month - 1]} {now.year} г."


def main() -> int:
    cfg = load_config()
    now = datetime.now(MSK)
    date_str = _date_str(now)
    print(f"[newsbot] запуск, дата (МСК): {date_str}")

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

    sections: list[digest.Section] = []
    for topic in TOPICS:
        headlines = sources.fetch_headlines(topic.feeds)
        print(f"[newsbot] тема «{topic.title}»: {len(headlines)} заголовков")
        section = digest.summarize_topic(deepseek, topic, headlines)
        if section:
            sections.append(section)

    if not sections:
        print("[newsbot] не удалось собрать ни одной новости — выходим")
        return 1

    try:
        message = digest.compose_digest(hermes, date_str, sections)
    except Exception as exc:  # noqa: BLE001 — лучше отправить черновик, чем ничего
        print(f"[newsbot] редактор Hermes недоступен ({exc}), резервная сборка")
        message = digest.assemble_plain(date_str, sections)

    message = digest.append_missing(message, sections)

    if cfg.dry_run:
        print("\n===== DRY RUN: итоговый дайджест =====\n")
        print(message)
        return 0

    telegram.send_message(cfg.telegram_token, cfg.telegram_chat_id, message)
    print("[newsbot] дайджест отправлен")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
