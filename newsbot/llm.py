"""Минимальный клиент для OpenAI-совместимых API (DeepSeek, OpenRouter/Hermes)."""

from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass
class ChatClient:
    api_key: str
    base_url: str
    model: str
    extra_headers: dict[str, str] | None = None

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
        timeout: int = 90,
    ) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
