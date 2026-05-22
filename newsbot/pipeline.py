"""Сборка дайджеста: общий код для крона (__main__) и слушателя (listen)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import digest, rates, sources
from .config import (
    TOPICS,
    TOURISM_FLIGHT_CHANNEL,
    TOURISM_TOUR_CHANNEL,
    TOURISM_WEBCAM_URL,
    Config,
    Topic,
)
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


def _first(headlines: list[sources.Headline]) -> sources.Headline | None:
    return headlines[0] if headlines else None


def _tourism_section(
    deepseek: ChatClient, topic: Topic, allowed: set[str]
) -> digest.Section | None:
    """Туризм: новость про визы (из лент) + билет и тур (из Telegram-каналов)."""
    visa_news = sources.filter_by_keywords(
        sources.fetch_headlines(topic.feeds), topic.keywords
    )
    visa = _first(visa_news)
    flight = _first(sources.fetch_telegram_channel(TOURISM_FLIGHT_CHANNEL, limit=3))
    tour = _first(sources.fetch_telegram_channel(TOURISM_TOUR_CHANNEL, limit=3))
    for h in (visa, flight, tour):
        if h and h.link:
            allowed.add(h.link)
    print(
        f"[pipeline] тема «{topic.title}»: визы={bool(visa)} "
        f"билет={bool(flight)} тур={bool(tour)}"
    )
    section = digest.build_tourism_section(deepseek, topic.title, visa, flight, tour)

    # Ссылка на веб-камеры Паттайи добавляется всегда (статичная).
    webcam = f'• Веб-камеры Паттайи: <a href="{TOURISM_WEBCAM_URL}">смотреть онлайн</a>'
    allowed.add(TOURISM_WEBCAM_URL)
    if section is None:
        return digest.Section(title=topic.title, bullets=webcam)
    section.bullets = f"{section.bullets}\n{webcam}"
    return section


def generate_digest(deepseek: ChatClient, hermes: ChatClient) -> str | None:
    """Собирает дайджест по всем темам. Возвращает готовый текст или None."""
    date_str = _date_str(datetime.now(MSK))
    print(f"[pipeline] сборка дайджеста, дата (МСК): {date_str}")

    sections: list[digest.Section] = []
    allowed: set[str] = set()  # ссылки, которым доверяем (реальные источники)

    for topic in TOPICS:
        if topic.key == "tourism":
            section = _tourism_section(deepseek, topic, allowed)
            if section:
                sections.append(section)
            continue

        headlines = sources.fetch_headlines(topic.feeds)
        headlines = sources.filter_by_keywords(headlines, topic.keywords)
        allowed.update(h.link for h in headlines if h.link)
        print(f"[pipeline] тема «{topic.title}»: {len(headlines)} заголовков")
        section = digest.summarize_topic(deepseek, topic, headlines)

        if topic.key == "dollar":
            try:
                rate_lines, rate_links = rates.rate_bullets()
            except Exception as exc:  # noqa: BLE001 — курсы необязательны, дайджест важнее
                print(f"[pipeline] курсы валют пропущены ({exc})")
                rate_lines, rate_links = [], set()
            if rate_lines:
                allowed |= rate_links
                prefix = "\n".join(rate_lines)
                if section is None:
                    section = digest.Section(title=topic.title, bullets=prefix)
                else:
                    section.bullets = f"{prefix}\n{section.bullets}"

        if section is None:
            continue

        sections.append(section)

    if not sections:
        print("[pipeline] не удалось собрать ни одной новости")
        return None

    try:
        message = digest.compose_digest(hermes, date_str, sections)
    except Exception as exc:  # noqa: BLE001 — лучше отправить черновик, чем ничего
        print(f"[pipeline] редактор Hermes недоступен ({exc}), резервная сборка")
        message = digest.assemble_plain(date_str, sections)

    message = digest.append_missing(message, sections)
    return digest.sanitize_links(message, allowed)
