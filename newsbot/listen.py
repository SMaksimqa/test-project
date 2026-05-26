"""Слушатель Telegram: по слову «новости» в чате присылает свежую сводку.

Два режима:
  • run()       — постоянный long-polling (для VPS/контейнера, ответ мгновенный);
  • poll_once() — однократная проверка (для GitHub Actions по расписанию,
                  ответ с задержкой до интервала запуска).

Отвечает в тот же чат, откуда пришёл триггер, поэтому подходит и для групп.
Важно для групп: у бота должен быть выключен режим приватности
(@BotFather → /setprivacy → Disable), иначе он не видит обычные сообщения.

Нельзя запускать оба режима одновременно: и long-polling, и опрос по
расписанию читают один и тот же поток getUpdates и будут мешать друг другу.
"""

from __future__ import annotations

import re
import sys
import time

import requests

from . import pipeline, telegram
from .config import Config, load_config
from .llm import ChatClient

# Слово «новости» как отдельное слово; срабатывает и на команду «/новости».
_TRIGGER = re.compile(r"(?<!\w)новости(?!\w)", re.IGNORECASE)
_BUSY = "Собираю свежую сводку, это займёт около минуты…"
_EMPTY = "Сейчас не удалось собрать новости, попробуйте чуть позже."
# В режиме опроса игнорируем триггеры старше этого возраста (защита от старого
# хвоста сообщений при первом запуске). Чуть больше интервала опроса.
_MAX_AGE_SEC = 1800


def _is_trigger(text: str) -> bool:
    return bool(text) and _TRIGGER.search(text) is not None


def _is_allowed(cfg: Config, chat_id: str) -> bool:
    """Пустой белый список → отвечаем всем; иначе только перечисленным чатам."""
    return not cfg.allowed_chat_ids or chat_id in cfg.allowed_chat_ids


def _deny(cfg: Config, msg: dict) -> None:
    """Отказ в доступе: в личке шлём ID юзера для админа, в группах — молча."""
    chat = msg["chat"]
    chat_id = str(chat["id"])
    user_id = msg.get("from", {}).get("id", chat["id"])
    print(f"[listen] доступ закрыт: чат {chat_id}, юзер {user_id}")
    if chat.get("type") == "private":
        text = (
            "Извини, бот приватный 🔒\n\n"
            f"Твой Telegram ID: {user_id}\n"
            "Передай его администратору, чтобы получить доступ."
        )
        telegram.send_message(cfg.telegram_token, chat_id, text)


def _respond(cfg: Config, deepseek: ChatClient, hermes: ChatClient, chat_id: str) -> None:
    print(f"[listen] триггер из чата {chat_id}")
    telegram.send_message(cfg.telegram_token, chat_id, _BUSY)
    message = pipeline.generate_digest(deepseek, hermes)
    telegram.send_message(cfg.telegram_token, chat_id, message or _EMPTY)


def run() -> None:
    """Постоянный long-polling. Подходит для всегда-онлайн хостинга (VPS)."""
    cfg = load_config()
    deepseek, hermes = pipeline.make_clients(cfg)
    api = f"https://api.telegram.org/bot{cfg.telegram_token}"
    offset: int | None = None
    print("[listen] long-polling запущен, жду слово «новости»…")

    while True:
        try:
            params: dict[str, object] = {"timeout": 50, "allowed_updates": '["message"]'}
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
            if not _is_allowed(cfg, chat_id):
                _deny(cfg, msg)
                continue
            try:
                _respond(cfg, deepseek, hermes, chat_id)
            except Exception as exc:  # noqa: BLE001 — один сбой не должен ронять слушатель
                print(f"[listen] ошибка ответа: {exc}")


def poll_once() -> None:
    """Однократная проверка для запуска по расписанию (GitHub Actions)."""
    cfg = load_config()
    api = f"https://api.telegram.org/bot{cfg.telegram_token}"

    resp = requests.get(
        f"{api}/getUpdates", params={"timeout": 0, "allowed_updates": '["message"]'}, timeout=30
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])
    if not updates:
        print("[listen] новых сообщений нет")
        return

    now = time.time()
    latest: dict[str, dict] = {}  # последний триггер в каждом чате
    for upd in updates:
        msg = upd.get("message")
        if not msg or not _is_trigger(msg.get("text", "")):
            continue
        if now - msg.get("date", 0) > _MAX_AGE_SEC:
            continue  # слишком старое — не отвечаем (но ниже подтвердим offset)
        chat_id = str(msg["chat"]["id"])
        if not _is_allowed(cfg, chat_id):
            _deny(cfg, msg)
            continue
        latest[chat_id] = msg

    if latest:
        deepseek, hermes = pipeline.make_clients(cfg)
        for chat_id in latest:
            try:
                _respond(cfg, deepseek, hermes, chat_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[listen] ошибка ответа в чат {chat_id}: {exc}")
    else:
        print("[listen] свежих триггеров «новости» нет")

    # Подтверждаем offset, чтобы следующий запуск не обрабатывал эти сообщения снова.
    last_id = max(upd["update_id"] for upd in updates)
    requests.get(f"{api}/getUpdates", params={"offset": last_id + 1, "timeout": 0}, timeout=30)
    print(f"[listen] обработано обновлений: {len(updates)}, offset подтверждён")


if __name__ == "__main__":
    if "poll" in sys.argv[1:]:
        poll_once()
    else:
        run()
