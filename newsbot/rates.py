"""Курсы валют для дайджеста: официальный ЦБ РФ + наличный курс Камкомбанка.

Подход и источники взяты из проекта morning-bot, но переписаны на requests
(без httpx/bs4), чтобы не плодить зависимости. Любой сбой сети не должен ронять
дайджест — функции возвращают None и пишут в лог.
"""

from __future__ import annotations

import re
import time
from xml.etree import ElementTree as ET

import requests

# Человеческая страница ЦБ — её показываем как ссылку «источник».
CBR_URL = "https://www.cbr.ru/currency_base/daily/"
# JSON-зеркало ЦБ: в одном ответе и текущее значение, и предыдущее (для дельты).
_CBR_JSON = "https://www.cbr-xml-daily.ru/daily_json.js"
# Официальный XML ЦБ — запасной источник, если зеркало недоступно.
_CBR_XML = "https://www.cbr.ru/scripts/XML_daily.asp"

KAMKOM_URL = "https://bankiros.ru/bank/kamkombank/currency/moskva"
_KAMKOM_OFFICE = "Чертановская"  # отделение на юге Москвы
_KAMKOM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}
_KAMKOM_NUMBER = re.compile(r"<span[^>]*>\s*(\d{2,3}[.,]\d{1,2})\s*</span>")


def _fmt(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _cbr_from_json() -> tuple[float, float] | None:
    """Текущее и предыдущее значение USD из JSON-зеркала ЦБ."""
    resp = requests.get(_CBR_JSON, timeout=15)
    resp.raise_for_status()
    usd = resp.json()["Valute"]["USD"]
    return float(usd["Value"]), float(usd["Previous"])


def _cbr_from_xml() -> tuple[float, float] | None:
    """Текущее значение USD из официального XML ЦБ (без предыдущего)."""
    resp = requests.get(_CBR_XML, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)  # bytes: учитывает windows-1251 из заголовка
    for valute in root.findall("Valute"):
        if valute.findtext("CharCode") != "USD":
            continue
        nominal = int(valute.findtext("Nominal") or "1")
        value = float((valute.findtext("Value") or "0").replace(",", "."))
        if nominal > 0:
            cur = value / nominal
            return cur, cur  # дельты нет — считаем «без изменений»
    return None


def _cbr_bullet() -> str | None:
    """Курс USD ЦБ: зеркало (с дельтой за день), при сбое — официальный XML."""
    pair = None
    for source in (_cbr_from_json, _cbr_from_xml):
        try:
            pair = source()
            if pair:
                break
        except Exception as exc:  # noqa: BLE001
            print(f"[rates] источник курса ЦБ недоступен ({source.__name__}): {exc}")
    if not pair:
        return None

    cur, prev = pair
    delta = cur - prev
    if delta > 0.005:
        move = f", растёт +{_fmt(delta)} ₽ за день"
    elif delta < -0.005:
        move = f", снижается −{_fmt(abs(delta))} ₽ за день"
    else:
        move = ""
    return f'• Курс ЦБ: {_fmt(cur)} ₽ за доллар{move}. <a href="{CBR_URL}">источник</a>'


def _kamkom_bullet() -> str | None:
    """Наличный курс доллара в Камкомбанке (отделение «Чертановская»)."""
    params = {"all": "1", "first_load": "1", "time": str(int(time.time() * 1000))}
    try:
        resp = requests.get(
            KAMKOM_URL, params=params, headers=_KAMKOM_HEADERS, timeout=15
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        print(f"[rates] курс Камкомбанка недоступен: {exc}")
        return None

    pos = html.find(_KAMKOM_OFFICE)
    if pos == -1:
        print(f"[rates] Камкомбанк: '{_KAMKOM_OFFICE}' не найден в ответе")
        return None

    chunk = html[pos : pos + 3000]
    candidates: list[float] = []
    for raw in _KAMKOM_NUMBER.findall(chunk):
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            continue
        if 50 < value < 150:
            candidates.append(value)
    if len(candidates) < 2:
        print(f"[rates] Камкомбанк: мало курсов рядом с офисом: {candidates}")
        return None

    buy, sell = candidates[0], candidates[1]
    if buy > sell:
        buy, sell = sell, buy
    return (
        f"• Камком (Чертановская): покупка {_fmt(buy)} ₽ / продажа {_fmt(sell)} ₽. "
        f'<a href="{KAMKOM_URL}">источник</a>'
    )


def rate_bullets() -> tuple[list[str], set[str]]:
    """Готовые пункты про курсы и набор их доверенных ссылок.

    Возвращает (список пунктов, множество URL для белого списка ссылок).
    """
    bullets: list[str] = []
    links: set[str] = set()

    cbr = _cbr_bullet()
    if cbr:
        bullets.append(cbr)
        links.add(CBR_URL)

    kamkom = _kamkom_bullet()
    if kamkom:
        bullets.append(kamkom)
        links.add(KAMKOM_URL)

    return bullets, links
