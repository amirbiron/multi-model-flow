"""
מודל Mistral AI
"""

from mistralai import Mistral
from .base import BaseModel, ModelResponse


class MistralModel(BaseModel):
    """מודל Mistral AI"""

    @property
    def name(self) -> str:
        return "Mistral"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Mistral ומחזיר תשובה"""
        try:
            client = Mistral(api_key=self.api_key)

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
            return ModelResponse(
                content="",
                model_name=self.name,
                success=False,
                error=str(e)
            )
