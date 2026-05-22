"""Курс доллара ЦБ РФ — публичный JSON, без ключей API."""

from __future__ import annotations

import requests

_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CBR_URL = "https://www.cbr.ru/currency_base/daily/"


def _fmt(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def usd_rub_bullet() -> str | None:
    """Готовый пункт про курс доллара ЦБ: уровень и изменение за день.

    Возвращает строку с «•» и ссылкой на ЦБ либо None, если данные недоступны.
    """
    try:
        resp = requests.get(_URL, timeout=15)
        resp.raise_for_status()
        usd = resp.json()["Valute"]["USD"]
        cur = float(usd["Value"])
        prev = float(usd["Previous"])
    except Exception as exc:  # noqa: BLE001 — нет курса не должно ронять дайджест
        print(f"[rates] курс ЦБ недоступен: {exc}")
        return None

    delta = cur - prev
    if delta > 0.005:
        move = f"растёт, +{_fmt(delta)} ₽ за день"
    elif delta < -0.005:
        move = f"снижается, −{_fmt(abs(delta))} ₽ за день"
    else:
        move = "почти без изменений"
    return f"• Курс ЦБ: {_fmt(cur)} ₽ за доллар ({move}). <a href=\"{_CBR}\">источник</a>"
