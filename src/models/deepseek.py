"""
מודל DeepSeek
"""

import asyncio
from openai import OpenAI
from .base import BaseModel, ModelResponse


class DeepSeekModel(BaseModel):
    """
    מודל DeepSeek.
    משתמש ב-OpenAI SDK עם base_url שונה.
    """

    @property
    def name(self) -> str:
        return "DeepSeek"

    def _sync_generate(self, prompt: str) -> ModelResponse:
        """קריאה סינכרונית ל-API"""
        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com"
            )

            response = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )

            content = response.choices[0].message.content

            return ModelResponse(
                content=content,
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
        """שולח prompt ל-DeepSeek ומחזיר תשובה (לא חוסם)"""
        return await asyncio.to_thread(self._sync_generate, prompt)
