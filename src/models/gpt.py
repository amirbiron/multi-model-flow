"""
מודל GPT (OpenAI)
"""

from openai import OpenAI
from .base import BaseModel, ModelResponse


class GPTModel(BaseModel):
    """מודל GPT של OpenAI"""

    @property
    def name(self) -> str:
        return "GPT"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-GPT ומחזיר תשובה"""
        try:
            client = OpenAI(api_key=self.api_key)

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
