from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


class LLMNotConfiguredError(RuntimeError):
    pass


@dataclass(slots=True)
class GroqClient:
    """
    Minimal Groq client for structured JSON resume extraction.
    Uses GROQ_API_KEY from the environment and the OpenAI-compatible chat endpoint.
    """

    api_key: Optional[str] = None
    model: str = "llama-3.3-70b-specdec"

    def _get_api_key(self) -> str:
        key = self.api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMNotConfiguredError("GROQ_API_KEY is not configured")
        return key

    def extract_resume(self, text: str) -> Dict[str, Any]:
        """
        Call Groq in JSON mode to extract structured resume data.
        This function is synchronous and intended to be easy to stub in tests.
        """
        api_key = self._get_api_key()
        if not text.strip():
            return {}

        prompt = (
            "You are a strict information extractor. "
            "Given a resume text, extract only values that literally appear in the text. "
            "If a field is not explicitly present, return null for it. "
            "Return a JSON object with keys: full_name, headline, emails, phones, "
            "locations, experiences, educations, skills. "
            "Each experience should have company, title, start, end. "
            "Each education should have school, degree, field_of_study, start, end. "
            "All dates must be strings from the text; do not invent months or years."
        )

        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Groq exposes an OpenAI-compatible API; this URL matches that shape.
        url = "https://api.groq.com/openai/v1/chat/completions"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

