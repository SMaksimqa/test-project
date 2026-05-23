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


# Telegram-каналы для раздела «Туризм» (читаются через публичный веб-предпросмотр
# t.me/s/<канал>, без токенов). Подаются как отдельные строки: билет и тур.
TOURISM_FLIGHT_CHANNEL = "ticketsthailand"
TOURISM_TOUR_CHANNELS = ("vandroukitours", "hkt_bkk", "vandroukiru")
# Поиск туров — запасная ссылка, если в каналах нет туров с ценой.
TOURISM_TOUR_SEARCH_URL = "https://www.onlinetours.ru/"

# Онлайн веб-камеры Паттайи — добавляем ссылкой в раздел «Туризм».
TOURISM_WEBCAM_URL = "https://ioc.pattaya.go.th/live-cctv/CC-024"


# Темы дайджеста и их RSS-источники (русскоязычные, без ключей API).
# Если лента недоступна, она пропускается, остальные продолжают работать.
# Порядок разделов в дайджесте совпадает с порядком в этом кортеже.
TOPICS: tuple[Topic, ...] = (
    Topic(
        key="world",
        title="🌍 В мире",
        feeds=(
            "https://tass.ru/rss/v2.xml",
            "https://nplus1.ru/rss",
        ),
        focus=(
            "Бери самое значимое в мире, но подавай нейтрально или позитивно: "
            "без чернухи, криминала, катастроф и сводок с фронтов. Уместны "
            "наука, открытия, культура, технологии, добрые события. Дай 2–3 "
            "коротких пункта."
        ),
    ),
    Topic(
        key="moscow",
        title="🏙 Москва",
        feeds=(
            "https://news.google.com/rss/search?q=%D0%91%D0%B8%D1%80%D1%8E%D0%BB%D1%91%D0%B2%D1%81%D0%BA%D0%B0%D1%8F%20%D0%BB%D0%B8%D0%BD%D0%B8%D1%8F%20%D0%BC%D0%B5%D1%82%D1%80%D0%BE%20%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%BE&hl=ru&gl=RU&ceid=RU:ru",
            "https://news.google.com/rss/search?q=%D0%94%D1%80%D0%BE%D0%B6%D0%B6%D0%B8%D0%BD%D0%BE%20%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D0%B8%20%D0%B7%D0%B0%D1%81%D1%82%D1%80%D0%BE%D0%B9%D0%BA%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
            "https://news.google.com/rss/search?q=%D1%82%D1%80%D0%B0%D1%81%D1%81%D0%B0%20%D0%A1%D0%BE%D0%BB%D0%BD%D1%86%D0%B5%D0%B2%D0%BE%20%D0%91%D1%83%D1%82%D0%BE%D0%B2%D0%BE%20%D0%92%D0%B0%D1%80%D1%88%D0%B0%D0%B2%D1%81%D0%BA%D0%BE%D0%B5%20%D1%88%D0%BE%D1%81%D1%81%D0%B5%20%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%BE&hl=ru&gl=RU&ceid=RU:ru",
            "https://news.google.com/rss/search?q=%D0%A1%D0%B8%D0%BC%D1%84%D0%B5%D1%80%D0%BE%D0%BF%D0%BE%D0%BB%D1%8C%D1%81%D0%BA%D0%BE%D0%B5%20%D1%88%D0%BE%D1%81%D1%81%D0%B5%20%D1%80%D0%B5%D0%BA%D0%BE%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F&hl=ru&gl=RU&ceid=RU:ru",
            "https://news.google.com/rss/search?q=%D1%8E%D0%B3%20%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D1%8B%20%D0%AE%D0%90%D0%9E%20%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D0%B8&hl=ru&gl=RU&ceid=RU:ru",
        ),
        focus=(
            "Новости юга Москвы и ближнего Подмосковья. Приоритетные темы, бери "
            "их в первую очередь, если есть свежие новости: строительство "
            "Бирюлёвской линии метро; развитие и застройка района Дрожжино; "
            "дороги — строительство трассы Солнцево–Бутово–Варшавское шоссе и "
            "реконструкция Симферопольского шоссе. Если по этим темам новостей "
            "нет — добавь общие новости юга города (ЮАО). Дай 3–4 конкретных "
            "пункта."
        ),
    ),
    Topic(
        key="dollar",
        title="💵 Доллар",
        feeds=(
            "https://news.google.com/rss/search?q=%D0%BA%D1%83%D1%80%D1%81%20%D0%B4%D0%BE%D0%BB%D0%BB%D0%B0%D1%80%D0%B0%20%D0%BA%20%D1%80%D1%83%D0%B1%D0%BB%D1%8E&hl=ru&gl=RU&ceid=RU:ru",
        ),
        focus=(
            "Дай ровно 1 короткий пункт-контекст: чем объясняется движение "
            "рубля сейчас по свежим новостям (без конкретной цифры курса — "
            "точное значение добавляется отдельно). Без инвестиционных советов "
            "и прогнозов покупки/продажи."
        ),
        keywords=("доллар", "рубл", "валют", "цб"),
    ),
    Topic(
        key="tourism",
        title="🧳 Туризм",
        feeds=(
            "https://news.google.com/rss/search?q=%D0%B2%D0%B8%D0%B7%D0%B0%20%D0%B1%D0%B5%D0%B7%D0%B2%D0%B8%D0%B7%20%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0%20%D0%B2%D1%8A%D0%B5%D0%B7%D0%B4%D0%B0%20%D0%B4%D0%BB%D1%8F%20%D1%82%D1%83%D1%80%D0%B8%D1%81%D1%82%D0%BE%D0%B2&hl=ru&gl=RU&ceid=RU:ru",
        ),
        focus=(
            "Одна строка-новость про визы и правила въезда для туристов "
            "(например: страна ввела/отменила визу, безвиз, изменила срок "
            "пребывания). Конкретно и по делу, без воды."
        ),
        keywords=("виз", "безвиз", "въезд", "паспорт", "турист"),
    ),
    Topic(
        key="it",
        title="💻 IT и технологии",
        feeds=(
            "https://habr.com/ru/rss/articles/?fl=ru",
            "https://3dnews.ru/news/rss/",
        ),
        focus="Дай ровно 4 новости — самые значимые и интересные.",
    ),
    Topic(
        key="gadgets",
        title="📱 Гаджеты",
        feeds=(
            "https://3dnews.ru/mobile/rss/",
            "https://www.ixbt.com/export/news.rss",
        ),
        focus=(
            "Это лента про гаджеты. Дай ровно 4 пункта. Подавай каждый пункт "
            "как живую новость, а не как карточку из магазина: сначала что "
            "произошло или что вышло и чем это интересно/необычно (главная "
            "фишка, кто производитель), затем при необходимости одна деталь. "
            "ВАЖНО: хотя бы в одном пункте обязательно укажи цену (бери её из "
            "заголовков, где она есть, — в рублях или долларах, как в "
            "источнике). Не выдумывай цену, если её нет ни в одном заголовке. "
            "Допускается лёгкая ирония. Избегай рекламного тона и сухого "
            "перечисления характеристик."
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
