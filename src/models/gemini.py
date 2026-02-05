"""
מודל Gemini (Google)
משתמש ב-SDK החדש google-genai
"""

from google import genai
from google.genai import types
from .base import BaseModel, ModelResponse


class GeminiModel(BaseModel):
    """מודל Gemini של Google"""

    @property
    def name(self) -> str:
        return "Gemini"

    async def generate(self, prompt: str) -> ModelResponse:
        """שולח prompt ל-Gemini ומחזיר תשובה"""
        try:
            client = genai.Client(api_key=self.api_key)

            response = client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=4096,
                )
            )

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
