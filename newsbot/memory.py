"""Память о уже показанных URL — чтобы новости не повторялись из выпуска в выпуск.

Хранится в JSON-файле на VPS. Путь задаётся переменной MEMORY_PATH; если
переменная не задана — память выключена (бот работает как раньше).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_LINK_RE = re.compile(r'<a href="([^"]+)"')


def _path() -> Path | None:
    raw = os.environ.get("MEMORY_PATH", "").strip()
    return Path(raw) if raw else None


def load_seen() -> set[str]:
    """Множество ранее показанных URL. Пустое — если файл недоступен."""
    p = _path()
    if not p or not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text() or "[]"))
    except Exception as exc:  # noqa: BLE001 — повреждённый файл не должен ронять бот
        print(f"[memory] не удалось прочитать {p}: {exc}")
        return set()


def extract_used(message: str) -> set[str]:
    """Все URL, реально попавшие в финальный текст дайджеста."""
    return set(_LINK_RE.findall(message))


def save_seen(used: set[str], keep: int = 200) -> None:
    """Дописывает свежие URL в начало списка, удаляет повторы, обрезает до keep."""
    p = _path()
    if not p or not used:
        return
    try:
        prev = json.loads(p.read_text()) if p.exists() else []
    except Exception:  # noqa: BLE001
        prev = []
    merged: list[str] = []
    seen: set[str] = set()
    for url in [*used, *prev]:
        if url in seen:
            continue
        seen.add(url)
        merged.append(url)
        if len(merged) >= keep:
            break
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False))
        tmp.replace(p)  # атомарная замена — не битый файл при сбое
    except Exception as exc:  # noqa: BLE001
        print(f"[memory] не удалось сохранить {p}: {exc}")
