"""
מודל Mistral AI
"""

import asyncio
import time
from mistralai.client import Mistral
from .base import BaseModel, ModelResponse

# timeout ארוך + retry בסיסי כדי להתמודד עם קריאות איטיות של Mistral
_TIMEOUT_MS = 120_000
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 2


class MistralModel(BaseModel):
    """מודל Mistral AI"""

    @property
    def name(self) -> str:
        return "Mistral"

    def _sync_generate(self, prompt: str) -> ModelResponse:
        """קריאה סינכרונית ל-API עם retry על כשלי רשת/timeout"""
        client = Mistral(api_key=self.api_key, timeout_ms=_TIMEOUT_MS)
        last_error: Exception | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = client.chat.complete(
                    model=self.model_id,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content
                return ModelResponse(
                    content=content,
                    model_name=self.name,
                    success=True
                )
            except Exception as e:
                last_error = e
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_BACKOFF_SECONDS * attempt)

        return ModelResponse(
            content="",
            model_name=self.name,
            success=False,
            error=str(last_error) if last_error else "unknown error"
        )

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Mistral ומחזיר תשובה (לא חוסם)"""
        return await asyncio.to_thread(self._sync_generate, prompt)
