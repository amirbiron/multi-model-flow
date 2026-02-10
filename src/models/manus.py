"""
מודל Manus

מימוש דרך OpenAI SDK במצב API תואם-OpenAI (Compatible Mode).
"""

import asyncio
from openai import OpenAI

from .base import BaseModel, ModelResponse


class ManusModel(BaseModel):
    """
    מודל Manus.
    משתמש ב-OpenAI SDK עם base_url תואם-OpenAI שמוגדר דרך קונפיג.
    """

    def __init__(self, api_key: str, model_id: str, base_url: str):
        super().__init__(api_key=api_key, model_id=model_id)
        self.base_url = base_url

    @property
    def name(self) -> str:
        return "Manus"

    def _sync_generate(self, prompt: str) -> ModelResponse:
        """קריאה סינכרונית ל-API"""
        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
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
        """שולח prompt ל-Manus ומחזיר תשובה (לא חוסם)"""
        return await asyncio.to_thread(self._sync_generate, prompt)
