"""Слушатель Telegram: по слову «новости» в чате присылает свежую сводку.

Работает через long-polling (getUpdates) и должен быть запущен постоянно
(24/7) — например, на VPS под systemd или в контейнере. Отвечает в тот же
чат, откуда пришёл триггер, поэтому подходит и для групповых чатов.

Важно для групп: у бота должен быть выключен режим приватности
(@BotFather → /setprivacy → Disable), иначе он не видит обычные сообщения,
а только команды и ответы на себя.
"""

from __future__ import annotations

import re
import time

import requests

from . import pipeline, telegram
from .config import load_config

# Слово «новости» как отдельное слово; срабатывает и на команду «/новости».
_TRIGGER = re.compile(r"(?<!\w)новости(?!\w)", re.IGNORECASE)
_BUSY = "Собираю свежую сводку, это займёт около минуты…"
_EMPTY = "Сейчас не удалось собрать новости, попробуйте чуть позже."


def _is_trigger(text: str) -> bool:
    return bool(text) and _TRIGGER.search(text) is not None


def run() -> None:
    cfg = load_config()
    deepseek, hermes = pipeline.make_clients(cfg)
    api = f"https://api.telegram.org/bot{cfg.telegram_token}"
    offset: int | None = None
    print("[listen] запущен, жду слово «новости»…")

    while True:
        try:
            params = {"timeout": 50, "allowed_updates": '["message"]'}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(f"{api}/getUpdates", params=params, timeout=65)
            resp.raise_for_status()
            updates = resp.json().get("result", [])
        except requests.RequestException as exc:
            print(f"[listen] сетевая ошибка ({exc}), пауза 5с")
            time.sleep(5)
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message")
            if not msg or not _is_trigger(msg.get("text", "")):
                continue
            chat_id = str(msg["chat"]["id"])
            print(f"[listen] триггер из чата {chat_id}")
            try:
                telegram.send_message(cfg.telegram_token, chat_id, _BUSY)
                message = pipeline.generate_digest(deepseek, hermes)
                telegram.send_message(cfg.telegram_token, chat_id, message or _EMPTY)
            except Exception as exc:  # noqa: BLE001 — один сбой не должен ронять слушатель
                print(f"[listen] ошибка при ответе в чат {chat_id}: {exc}")


if __name__ == "__main__":
    run()
