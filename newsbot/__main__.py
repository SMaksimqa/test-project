"""Точка входа крона: собрать дайджест и отправить в Telegram (один раз)."""

from __future__ import annotations

from . import pipeline, telegram
from .config import load_config


def main() -> int:
    cfg = load_config()
    deepseek, hermes = pipeline.make_clients(cfg)

    message = pipeline.generate_digest(deepseek, hermes)
    if message is None:
        print("[newsbot] нечего отправлять — выходим")
        return 1

    if cfg.dry_run:
        print("\n===== DRY RUN: итоговый дайджест =====\n")
        print(message)
        return 0

    telegram.send_message(cfg.telegram_token, cfg.telegram_chat_id, message)
    print("[newsbot] дайджест отправлен")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
