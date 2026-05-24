"""Сборка дайджеста: общий код для крона (__main__) и слушателя (listen)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import digest, rates, sources
from .config import (
    TOPICS,
    TOURISM_FLIGHT_CHANNEL,
    TOURISM_TOUR_CHANNELS,
    TOURISM_TOUR_SEARCH_URL,
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


def _greeting_and_wish(now: datetime) -> tuple[str, str]:
    """Приветствие и пожелание по времени суток в Москве + текущее время."""
    hour = now.hour
    if 5 <= hour < 12:
        word, wish = "Доброе утро", "Хорошего дня! ☀️"
    elif 12 <= hour < 18:
        word, wish = "Добрый день", "Хорошего дня! ☀️"
    elif 18 <= hour < 23:
        word, wish = "Добрый вечер", "Доброго вечера! 🌆"
    else:
        word, wish = "Доброй ночи", "Спокойной ночи! 🌙"
    greeting = f"{word}! Москва, {now:%H:%M} · {_date_str(now)}"
    return greeting, wish


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

# Категории туров в порядке приоритета: Таиланд → Турция → Вьетнам → прочее.
_TOUR_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Таиланд", ("таиланд", "тайланд", "бангкок", "пхукет", "паттай", "краби", "самуи")),
    ("Турция", ("турци", "анталь", "кемер", "белек", "аланья", "сиде", "мармарис")),
    ("Вьетнам", ("вьетнам", "нячанг", "фукуок", "дананг", "ханой", "фантьет")),
)


def _from_moscow(text: str) -> bool:
    """Вылет/прилёт связан с Москвой (другие города РФ отсекаем)."""
    return "москв" in text.lower()


def _pick_flight(posts: list[sources.Headline]) -> sources.Headline | None:
    """Билет только из Москвы, по приоритету направлений (Бангкок — первым)."""
    posts = [p for p in posts if _from_moscow(p.title)]
    for group in _FLIGHT_PRIORITY:
        for post in posts:  # posts идут от свежих к старым
            if any(kw in post.title.lower() for kw in group):
                return post
    return _first(posts)


def _tour_category(text: str) -> str:
    low = text.lower()
    for name, kws in _TOUR_CATEGORIES:
        if any(k in low for k in kws):
            return name
    return "Другое"


def _pick_tours(posts: list[sources.Headline], limit: int = 3) -> list[sources.Headline]:
    """До трёх туров из Москвы, с ценой, по одному на направление (приоритет выше)."""
    by_cat: dict[str, list[sources.Headline]] = {}
    for post in posts:
        if not _from_moscow(post.title) or sources.min_price_rub(post.title) is None:
            continue
        by_cat.setdefault(_tour_category(post.title), []).append(post)

    def best(group: list[sources.Headline]) -> sources.Headline:
        hot = [p for p in group if "горящ" in p.title.lower()]
        return min(hot or group, key=lambda p: sources.min_price_rub(p.title) or 0)

    priority = [name for name, _ in _TOUR_CATEGORIES]
    order = priority + [c for c in by_cat if c not in priority]
    result: list[sources.Headline] = []
    for cat in order:
        if cat in by_cat and len(result) < limit:
            result.append(best(by_cat[cat]))
    return result


def _tourism_section(
    deepseek: ChatClient, topic: Topic, allowed: set[str]
) -> digest.Section | None:
    """Туризм: визы (ленты) + билет и до трёх туров (Telegram-каналы)."""
    visa_news = sources.filter_by_keywords(
        sources.fetch_headlines(topic.feeds), topic.keywords
    )
    visa = _first(visa_news)
    flight = _pick_flight(sources.fetch_telegram_channel(TOURISM_FLIGHT_CHANNEL, limit=25))

    tour_posts: list[sources.Headline] = []
    for channel in TOURISM_TOUR_CHANNELS:
        tour_posts += sources.fetch_telegram_channel(channel, limit=20)
    tours = _pick_tours(tour_posts)

    for h in [visa, flight, *tours]:
        if h and h.link:
            allowed.add(h.link)
    print(
        f"[pipeline] тема «{topic.title}»: визы={bool(visa)} "
        f"билет={bool(flight)} туров={len(tours)}"
    )
    section = digest.build_tourism_section(deepseek, topic.title, visa, flight, tours)

    extra = []
    if not tours:  # туров с ценой не нашли — даём ссылку на поиск
        extra.append(f'• Туры: подобрать на <a href="{TOURISM_TOUR_SEARCH_URL}">onlinetours.ru</a>')
        allowed.add(TOURISM_TOUR_SEARCH_URL)
    extra.append(f'• Веб-камеры Паттайи: <a href="{TOURISM_WEBCAM_URL}">смотреть онлайн</a>')
    allowed.add(TOURISM_WEBCAM_URL)

    extra_text = "\n".join(extra)
    if section is None:
        return digest.Section(title=topic.title, bullets=extra_text)
    section.bullets = f"{section.bullets}\n{extra_text}"
    return section


def generate_digest(deepseek: ChatClient, hermes: ChatClient) -> str | None:
    """Собирает дайджест по всем темам. Возвращает готовый текст или None."""
    now = datetime.now(MSK)
    greeting, wish = _greeting_and_wish(now)
    print(f"[pipeline] сборка дайджеста, {greeting}")

    sections: list[digest.Section] = []
    allowed: set[str] = set()  # ссылки, которым доверяем (реальные источники)

    for topic in TOPICS:
        if topic.key == "tourism":
            section = _tourism_section(deepseek, topic, allowed)
            if section:
                sections.append(section)
            continue

        if topic.key == "dollar":
            # Только курсы (ЦБ + Камком) с прямыми ссылками — без новостных лент.
            try:
                rate_lines, rate_links = rates.rate_bullets()
            except Exception as exc:  # noqa: BLE001 — курсы необязательны, дайджест важнее
                print(f"[pipeline] курсы валют пропущены ({exc})")
                rate_lines, rate_links = [], set()
            print(f"[pipeline] тема «{topic.title}»: курсов {len(rate_lines)}")
            if rate_lines:
                allowed |= rate_links
                sections.append(
                    digest.Section(title=topic.title, bullets="\n".join(rate_lines))
                )
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
        if section is None:
            continue

        sections.append(section)

    if not sections:
        print("[pipeline] не удалось собрать ни одной новости")
        return None

    message = digest.compose_digest(greeting, wish, sections)
    message = digest.sanitize_links(message, allowed)
    return digest.harden_html(message)
