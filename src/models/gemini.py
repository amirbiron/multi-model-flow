"""
מודל Gemini (Google)
"""

import asyncio
import google.generativeai as genai
from .base import BaseModel, ModelResponse


class GeminiModel(BaseModel):
    """מודל Gemini של Google"""

    @property
    def name(self) -> str:
        return "Gemini"

    def _sync_generate(self, prompt: str) -> ModelResponse:
        """קריאה סינכרונית ל-API"""
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_id)

            response = model.generate_content(prompt)

            return ModelResponse(
                content=response.text,
                model_name=self.name,
                success=True
            )

        except Exception as e:
            return ModelResponse(
                content="",
                model_name=self.name,
                success=False,
                error=str(e)
            )

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Gemini ומחזיר תשובה (לא חוסם)"""
        return await asyncio.to_thread(self._sync_generate, prompt)
