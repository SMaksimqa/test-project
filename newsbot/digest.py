"""Двухступенчатый конвейер: DeepSeek суммирует, Hermes редактирует дайджест."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Topic
from .llm import ChatClient
from .sources import Headline, format_for_prompt

_SUMMARIZER_SYSTEM = (
    "Ты — ведущий тёплой авторской рассылки, а не сухой агрегатор новостей. "
    "Тебе дают свежие заголовки и краткие описания по одной теме. Сделай "
    "выжимку строго по фактам из материалов — без выдумок, — но подача ДОЛЖНА "
    "быть живой: разговорная интонация, лёгкий юмор и неожиданные сравнения "
    "там, где уместно, угол зрения «почему это вообще интересно», а не «вот "
    "факт, прими». Никаких пресс-релизных клише и канцелярита. По умолчанию "
    "3–5 пунктов, но если в указании задано другое число — точно следуй ему. "
    "Каждый пункт на русском — одно ёмкое живое предложение (можно чуть "
    "длиннее, если так интереснее), начинается с «•». Не добавляй вступлений "
    "и заголовков.\n"
    "В САМОМ КОНЦЕ каждого пункта поставь РОВНО ОДИН номер источника в "
    "квадратных скобках — например [3], — взяв номер соответствующего "
    "заголовка из списка. Не ставь несколько номеров, не пиши ссылок и URL — "
    "только один номер в скобках."
)

_LINK_RE = re.compile(r"""<a\s+href=(["'])(.*?)\1[^>]*>(.*?)</a>""", re.DOTALL | re.IGNORECASE)


@dataclass
class Section:
    title: str
    bullets: str  # готовые пункты от DeepSeek


_SRC_MARKER_RE = re.compile(r"\s*\[(\d{1,2})\]")
# Несколько ссылок «источник» подряд → оставляем одну.
_DUP_SRC_RE = re.compile(
    r'(<a href="[^"]*">источник</a>)(?:\s*<a href="[^"]*">источник</a>)+'
)


def _attach_sources(text: str, headlines: list[Headline]) -> str:
    """Заменяет маркеры [N] на ссылку соответствующего источника.

    Модель выдаёт короткий номер вместо длинного URL — так ответ не обрывается
    на середине ссылки и тег всегда остаётся целым.
    """

    def repl(m: re.Match[str]) -> str:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(headlines) and headlines[idx].link:
            return f' <a href="{headlines[idx].link}">источник</a>'
        return ""

    return _DUP_SRC_RE.sub(r"\1", _SRC_MARKER_RE.sub(repl, text))


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
    return Section(title=topic.title, bullets=_attach_sources(bullets.strip(), headlines))


_WC_SYSTEM = (
    "Ты — спортивный редактор. На вход — заголовки и описания свежих новостей "
    "про Чемпионат мира по футболу 2026. Тебе указаны две даты — «вчера» и "
    "«сегодня» — и список материалов. Извлеки из материалов СТРОГО факты — "
    "без выдумок — в следующем формате (только эти строки и пункты, ничего "
    "лишнего):\n\n"
    "<b>Вчера:</b>\n"
    "• Команда1 X:Y Команда2 [N]\n"
    "(одна строка на матч; перечисли ВСЕ матчи, которые упомянуты в "
    "заголовках/описаниях как сыгранные вчера — не пропускай ни одного)\n\n"
    "<b>Сегодня:</b>\n"
    "• Команда1 — Команда2, ЧЧ:ММ МСК "
    "(Матч ТВ / Матч! Премьер / без ТВ / уточняется) [N]\n"
    "(одна строка на матч; перечисли ВСЕ матчи, которые упомянуты в "
    "заголовках/описаниях как сегодняшние — не пропускай ни одного)\n\n"
    "Правила:\n"
    "- Внимательно прочитай ВСЕ заголовки и описания, в т.ч. «обзоры», "
    "«анонсы», «расписание», «итоги». Матчи часто разбросаны по разным новостям.\n"
    "- ВАЖНО: если в заголовке упомянут вчерашний матч — он ОБЯЗАН попасть в "
    "блок «Вчера», даже если точный счёт не указан. В этом случае пиши "
    "«Команда1 — Команда2 (счёт уточняется)». То же про сегодняшний "
    "матч и время.\n"
    "- Косвенные упоминания тоже считаются: «Аргентина обыграла Канаду», "
    "«Германия не справилась с Японией» — это вчерашние матчи, выводи их.\n"
    "- Если один и тот же матч упомянут в нескольких источниках — выведи его "
    "ОДИН раз и не дублируй.\n"
    "- Команды, счёт, время и трансляцию бери ТОЛЬКО из материалов. Не выдумывай.\n"
    "- Пропускай блок («Вчера» или «Сегодня») ТОЛЬКО если в материалах нет "
    "НИ ОДНОГО упоминания матча за эту дату.\n"
    "- Если ни по одной из дат данных нет — верни ровно одну строку: "
    "«• Расписание матчей уточняется».\n"
    "- В САМОМ КОНЦЕ каждого пункта «•» поставь ровно ОДИН номер источника [N] "
    "из списка заголовков. Без URL и без нескольких номеров."
)


def summarize_worldcup(
    deepseek: ChatClient,
    topic: Topic,
    headlines: list[Headline],
    today_label: str,
    yesterday_label: str,
) -> Section | None:
    """Раздел ЧМ-2026: матчи вчера со счётом + сегодня с временем и каналом."""
    if not headlines:
        print(f"[digest] нет свежих материалов по теме «{topic.title}»")
        return None
    user = (
        f"Сегодня: {today_label}\n"
        f"Вчера: {yesterday_label}\n\n"
        "Заголовки:\n" + format_for_prompt(headlines)
    )
    bullets = deepseek.complete(_WC_SYSTEM, user, temperature=0.2, max_tokens=1000)
    return Section(title=topic.title, bullets=_attach_sources(bullets.strip(), headlines))


def sanitize_links(text: str, allowed: set[str]) -> str:
    """Оставляет только ссылки из набора allowed; чужие/выдуманные — разворачивает в текст."""

    def repl(m: re.Match[str]) -> str:
        url = m.group(2).strip()
        inner = m.group(3)
        if url in allowed:
            return f'<a href="{url}">{inner}</a>'
        return inner  # ссылки нет в списке источников — убираем тег, текст оставляем

    return _LINK_RE.sub(repl, text)


# Теги, которые Telegram разрешает в режиме HTML и которые мы сами расставляем.
_SAFE_TAG_RE = re.compile(r'</?[bi]>|<a href="[^"]*">|</a>', re.IGNORECASE)
_HREF_RE = re.compile(r'<a href="([^"]*)">', re.IGNORECASE)


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def harden_html(text: str) -> str:
    """Делает текст валидным Telegram-HTML.

    Экранирует «голые» &, <, > в тексте и & внутри href, сохраняя наши теги
    (<b>, <i>, <a href>). Без этого Telegram отвечает 400, и сообщение уходит
    как plain-текст с «сырыми» тегами.
    """
    out: list[str] = []
    pos = 0
    for m in _SAFE_TAG_RE.finditer(text):
        out.append(_escape_text(text[pos : m.start()]))
        tag = m.group(0)
        href = _HREF_RE.match(tag)
        if href:
            safe = href.group(1).replace("&", "&amp;")
            tag = f'<a href="{safe}">'
        out.append(tag)
        pos = m.end()
    out.append(_escape_text(text[pos:]))
    return "".join(out)


_FLIGHT_LINE_SYSTEM = (
    "Ты сжимаешь пост авиа-канала в ОДНУ короткую строку на русском. Укажи "
    "маршрут (откуда → куда), цену в рублях (она есть в тексте) и одну деталь "
    "(даты или туда-обратно / в одну сторону). Без эмодзи-мусора, хэштегов и "
    "призывов подписаться. Не выдумывай данные. Верни только строку — без «•» "
    "и без ссылок."
)

_TOUR_LINE_SYSTEM = (
    "Ты сжимаешь пост тревел-канала о туре в ОДНУ короткую строку на русском "
    "для семейного дайджеста. ОБЯЗАТЕЛЬНО укажи: страну и город/курорт, отель "
    "и его звёздность (если есть), цену в рублях (она есть в тексте) и одну "
    "деталь (даты, питание / «всё включено», сколько ночей). Конкретно, без "
    "воды. Без эмодзи-мусора, хэштегов и призывов подписаться. Не выдумывай "
    "данные. Верни только строку — без «•» и без ссылок."
)

_VISA_LINE_SYSTEM = (
    "Сожми новость про визы и правила въезда в одну короткую строку на русском: "
    "какая страна и что именно изменилось (ввела/отменила визу, безвиз, срок "
    "пребывания). Только факт, без воды, без «•» и без ссылок."
)


def _deal_line(
    deepseek: ChatClient, post: Headline | None, label: str, system: str
) -> str | None:
    if post is None:
        return None
    text = deepseek.complete(system, post.title, temperature=0.3, max_tokens=200)
    text = text.strip().lstrip("•").strip()
    if not text:
        return None
    link = f' <a href="{post.link}">подробнее</a>' if post.link else ""
    return f"• {label}: {text}{link}"


def build_tourism_section(
    deepseek: ChatClient,
    title: str,
    visa: Headline | None,
    flight: Headline | None,
    tours: list[Headline],
) -> Section | None:
    """Туризм: новость про визы, авиабилет (из Москвы) и до трёх туров."""
    lines: list[str] = []

    if visa is not None:
        src = f"{visa.title}. {visa.summary}".strip()
        text = deepseek.complete(_VISA_LINE_SYSTEM, src, temperature=0.3, max_tokens=160)
        text = text.strip().lstrip("•").strip()
        if text:
            link = f' <a href="{visa.link}">источник</a>' if visa.link else ""
            lines.append(f"• Визы: {text}{link}")

    flight_line = _deal_line(deepseek, flight, "Авиабилет", _FLIGHT_LINE_SYSTEM)
    if flight_line:
        lines.append(flight_line)

    for tour in tours:
        tour_line = _deal_line(deepseek, tour, "Тур", _TOUR_LINE_SYSTEM)
        if tour_line:
            lines.append(tour_line)

    if not lines:
        print("[digest] раздел «Туризм»: нет данных ни по одной строке")
        return None
    return Section(title=title, bullets="\n".join(lines))


def compose_digest(greeting: str, wish: str, sections: list[Section]) -> str:
    """Детерминированная сборка: каждый раздел гарантированно со своим заголовком.

    Приветствие и пожелание формируются по времени МСК (см. pipeline), структуру
    не доверяем модели — она склонна склеивать разделы и терять ссылки.
    """
    parts = [f"<b>{greeting}</b>", ""]
    for section in sections:
        parts.append(f"<b>{section.title}</b>")
        parts.append(section.bullets)
        parts.append("")
    parts.append(wish)
    return "\n".join(parts).strip()
