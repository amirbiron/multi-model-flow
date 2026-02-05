"""
מודל Perplexity (Sonar)
לחיפוש איכותי ואמין ברשת
"""

from openai import OpenAI
from .base import BaseModel, ModelResponse


class PerplexityModel(BaseModel):
    """
    מודל Perplexity (Sonar).
    מיוחד לחיפוש ברשת - כולל מקורות ומידע עדכני.
    משתמש ב-OpenAI SDK עם base_url שונה.
    """

    @property
    def name(self) -> str:
        return "Perplexity"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Perplexity ומחזיר תשובה עם מקורות"""
        try:
            # Perplexity משתמש ב-OpenAI-compatible API
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.perplexity.ai"
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
