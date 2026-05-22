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


# Приоритет направлений для авиабилетов: Бангкок → Пхукет → Вьетнам → остальное.
_FLIGHT_PRIORITY: tuple[tuple[str, ...], ...] = (
    ("бангкок", "bangkok", "bkk"),
    ("пхукет", "phuket", "hkt"),
    ("вьетнам", "vietnam", "ханой", "нячанг", "дананг", "фукуок", "хошимин"),
)


def _pick_flight(posts: list[sources.Headline]) -> sources.Headline | None:
    """Выбирает билет по приоритету направлений (Бангкок — в первую очередь)."""
    for group in _FLIGHT_PRIORITY:
        for post in posts:  # posts идут от свежих к старым
            if any(kw in post.title.lower() for kw in group):
                return post
    return _first(posts)  # нет приоритетных — берём самый свежий


def _pick_tour(posts: list[sources.Headline]) -> sources.Headline | None:
    """Выбирает тур с ОБЯЗАТЕЛЬНОЙ ценой: приоритет горящим и самым дешёвым."""
    priced = [(p, sources.min_price_rub(p.title)) for p in posts]
    priced = [(p, v) for p, v in priced if v is not None]
    if not priced:
        return None  # без цены тур не показываем
    hot = [(p, v) for p, v in priced if "горящ" in p.title.lower()]
    pool = hot or priced
    pool.sort(key=lambda pv: pv[1])  # самый дешёвый первым
    return pool[0][0]


def _tourism_section(
    deepseek: ChatClient, topic: Topic, allowed: set[str]
) -> digest.Section | None:
    """Туризм: новость про визы (из лент) + билет и тур (из Telegram-каналов)."""
    visa_news = sources.filter_by_keywords(
        sources.fetch_headlines(topic.feeds), topic.keywords
    )
    visa = _first(visa_news)
    flight = _pick_flight(sources.fetch_telegram_channel(TOURISM_FLIGHT_CHANNEL, limit=25))
    tour = _pick_tour(sources.fetch_telegram_channel(TOURISM_TOUR_CHANNEL, limit=25))
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
        if topic.key == "gadgets":
            # Поднимаем наверх новости с ценой, чтобы хотя бы одна попала в выжимку.
            headlines.sort(
                key=lambda h: not sources.has_price(f"{h.title} {h.summary}")
            )
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

    message = digest.compose_digest(hermes, date_str, sections)
    return digest.sanitize_links(message, allowed)
