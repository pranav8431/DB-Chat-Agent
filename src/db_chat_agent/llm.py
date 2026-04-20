from __future__ import annotations

from typing import Any

import requests

from .config import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> str:
        provider = self.settings.llm_provider.lower().strip()
        if provider == "ollama":
            return self._chat_ollama(system_prompt, user_prompt, temperature, max_tokens)
        if provider == "openai_compatible":
            return self._chat_openai_compatible(system_prompt, user_prompt, temperature, max_tokens)
        raise ValueError(f"Unsupported LLM provider: {self.settings.llm_provider}")

    def _chat_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        url = f"{self.settings.llm_base_url.rstrip('/')}/api/chat"
        predict_tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": predict_tokens,
            },
        }
        response = requests.post(url, json=payload, timeout=self.settings.llm_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()

    def _chat_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        if not self.settings.llm_api_key:
            raise ValueError("LLM_API_KEY is required for openai_compatible provider.")

        url = f"{self.settings.llm_base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.settings.llm_max_tokens,
        }
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
