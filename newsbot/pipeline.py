"""Сборка дайджеста: общий код для крона (__main__) и слушателя (listen)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import digest, memory, rates, sources, tourism_tips
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
    deepseek: ChatClient, topic: Topic, allowed: set[str], seen: set[str],
    now_msk: datetime,
) -> digest.Section | None:
    """Туризм: лайфхак дня + авиабилет и до трёх туров (Telegram-каналы)."""
    flight_posts = [
        p for p in sources.fetch_telegram_channel(TOURISM_FLIGHT_CHANNEL, limit=25)
        if p.link not in seen
    ]
    flight = _pick_flight(flight_posts)

    tour_posts: list[sources.Headline] = []
    for channel in TOURISM_TOUR_CHANNELS:
        tour_posts += sources.fetch_telegram_channel(channel, limit=20)
    tour_posts = [p for p in tour_posts if p.link not in seen]
    tours = _pick_tours(tour_posts)

    for h in [flight, *tours]:
        if h and h.link:
            allowed.add(h.link)
    print(
        f"[pipeline] тема «{topic.title}»: билет={bool(flight)} туров={len(tours)}"
    )
    section = digest.build_tourism_section(deepseek, topic.title, None, flight, tours)

    # Лайфхак — первая строка раздела, всегда есть.
    tip = tourism_tips.tip_of_day(now_msk)
    head = f"• Лайфхак дня: {tip}"

    extra = []
    if not tours:  # туров с ценой не нашли — даём ссылку на поиск
        extra.append(f'• Туры: подобрать на <a href="{TOURISM_TOUR_SEARCH_URL}">onlinetours.ru</a>')
        allowed.add(TOURISM_TOUR_SEARCH_URL)
    extra.append(f'• Веб-камеры Паттайи: <a href="{TOURISM_WEBCAM_URL}">смотреть онлайн</a>')
    allowed.add(TOURISM_WEBCAM_URL)

    extra_text = "\n".join(extra)
    if section is None:
        return digest.Section(title=topic.title, bullets=f"{head}\n{extra_text}")
    section.bullets = f"{head}\n{section.bullets}\n{extra_text}"
    return section


# Канал, из которого берём «В мире» — последние самые залайканные посты за день.
_WORLD_CHANNEL = "pezduzalive"
# Рекламные маркеры в тексте поста. «erid» — обязательная пометка платных
# постов в РФ; «реклам» ловит «Реклама»/«рекламный»; «промокод» — частый
# признак рекламы товара.
_AD_TEXT_RE = re.compile(r"реклам|\berid\b|промокод|купон", re.IGNORECASE)
# Эмодзи-«клоун» — публика канала ставит её как пометку «это реклама».
_AD_REACTION = "🤡"
# В этом канале на каждом посте картинка, поэтому медиа-признак сам по себе
# не годится. Отсекаем только посты, где текста объективно мало для шутки —
# короткие «вот это да» / «хах» без контекста.
_CAPTION_MAX_LEN = 30


def _is_pezduza_ad(post: sources.ChannelPost) -> bool:
    if post.top_reaction == _AD_REACTION:
        return True
    return bool(_AD_TEXT_RE.search(post.text))


def _is_caption_only(post: sources.ChannelPost) -> bool:
    """Очень короткий текст обычно — подпись к мему, в digest без картинки бесполезен."""
    return len(post.text) < _CAPTION_MAX_LEN


def _world_section(allowed: set[str], seen: set[str]) -> digest.Section | None:
    """«В мире» = топ-5 постов pezduzalive за сутки по реакциям, без рекламы и подписей-затычек."""
    # Берём с запасом — после фильтрации должно остаться минимум 5 хороших постов.
    raw = sources.fetch_telegram_top(_WORLD_CHANNEL, hours=24, limit=30)
    posts: list[sources.ChannelPost] = []
    skipped = {"ad": 0, "caption": 0, "seen": 0}
    for p in raw:
        if p.link in seen:
            skipped["seen"] += 1
            continue
        if _is_pezduza_ad(p):
            skipped["ad"] += 1
            continue
        if _is_caption_only(p):
            skipped["caption"] += 1
            continue
        posts.append(p)
        if len(posts) >= 5:
            break
    print(
        f"[pipeline] тема «🌍 В мире»: годных {len(posts)} из сырых {len(raw)}, "
        f"отсеяно {skipped}"
    )
    if not posts:
        if raw:
            # Раз посты есть, но все отсеялись — печатаем причины первых трёх
            # сырых для диагностики (часто помогает понять, что не так).
            for p in raw[:3]:
                print(
                    f"[pipeline] sample: top_react={p.top_reaction!r} "
                    f"len={len(p.text)} media={p.has_media} "
                    f"text={p.text[:80]!r}"
                )
        return None
    lines: list[str] = []
    for p in posts:
        excerpt = p.text[:200].rstrip()
        if len(p.text) > 200:
            excerpt += "…"
        lines.append(f'• {excerpt} <a href="{p.link}">→</a>')
        allowed.add(p.link)
    return digest.Section(title="🌍 В мире", bullets="\n".join(lines))


def _worldcup_section(
    deepseek: ChatClient,
    topic: Topic,
    allowed: set[str],
    seen: set[str],
    now_msk: datetime,
) -> digest.Section | None:
    """ЧМ-2026: матчи вчера со счётом + сегодня с временем и каналом."""
    # Берём больше материалов на ленту — LLM должна увидеть как можно больше
    # упоминаний разных матчей дня.
    headlines = sources.fetch_headlines(topic.feeds, per_feed=20)
    headlines = sources.filter_by_keywords(headlines, topic.keywords)
    headlines = [h for h in headlines if h.link not in seen]
    allowed.update(h.link for h in headlines if h.link)
    print(f"[pipeline] тема «{topic.title}»: {len(headlines)} материалов (ищем матчи)")
    yest = now_msk - timedelta(days=1)
    return digest.summarize_worldcup(
        deepseek, topic, headlines, _date_str(now_msk), _date_str(yest)
    )


# URL, которые всегда должны появляться (курсы, вебкамеры, ссылка на поиск
# туров) — их НЕ запоминаем в антиповторе, иначе после первого выпуска бот
# больше никогда их не покажет.
_NEVER_REMEMBER = {
    rates.CBR_URL,
    rates.KAMKOM_URL,
    TOURISM_WEBCAM_URL,
    TOURISM_TOUR_SEARCH_URL,
}


def generate_digest(deepseek: ChatClient, hermes: ChatClient) -> str | None:
    """Собирает дайджест по всем темам. Возвращает готовый текст или None."""
    now = datetime.now(MSK)
    greeting, wish = _greeting_and_wish(now)
    print(f"[pipeline] сборка дайджеста, {greeting}")

    seen = memory.load_seen()
    if seen:
        print(f"[pipeline] память: {len(seen)} URL уже показывали, пропустим их")

    sections: list[digest.Section] = []
    allowed: set[str] = set()  # ссылки, которым доверяем (реальные источники)

    for topic in TOPICS:
        if topic.key == "world":
            section = _world_section(allowed, seen)
            if section:
                sections.append(section)
            continue

        if topic.key == "worldcup":
            section = _worldcup_section(deepseek, topic, allowed, seen, now)
            if section:
                sections.append(section)
            continue

        if topic.key == "tourism":
            section = _tourism_section(deepseek, topic, allowed, seen, now)
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
        headlines = [h for h in headlines if h.link not in seen]
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
    message = digest.harden_html(message)

    used = memory.extract_used(message) - _NEVER_REMEMBER
    memory.save_seen(used)
    return message
