"""
מודל Claude (Anthropic)
"""

import anthropic
from .base import BaseModel, ModelResponse


class ClaudeModel(BaseModel):
    """מודל Claude של Anthropic"""

    @property
    def name(self) -> str:
        return "Claude"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Claude ומחזיר תשובה"""
        try:
            client = anthropic.Anthropic(api_key=self.api_key)

            message = client.messages.create(
                model=self.model_id,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # חילוץ התוכן מהתשובה
            content = message.content[0].text

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
