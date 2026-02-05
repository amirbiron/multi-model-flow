"""
מודל Grok (xAI)
"""

from openai import OpenAI
from .base import BaseModel, ModelResponse


class GrokModel(BaseModel):
    """
    מודל Grok של xAI.
    משתמש ב-OpenAI SDK עם base_url שונה.
    """

    @property
    def name(self) -> str:
        return "Grok"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Grok ומחזיר תשובה"""
        try:
            # Grok משתמש ב-OpenAI-compatible API
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.x.ai/v1"
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
