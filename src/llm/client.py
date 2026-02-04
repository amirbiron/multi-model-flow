"""
Architect Agent - LLM Client
=============================
תמיכה ב-Claude ו-Gemini עם Factory Pattern לבחירת ספק.
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional, List, Dict, Any
from pydantic import BaseModel
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """
    ממשק בסיסי ל-LLM clients.
    מגדיר את המתודות שכל ספק צריך לממש.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """יצירת תשובה טקסטית."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> T:
        """יצירת תשובה מובנית לפי Pydantic model."""
        pass

    @abstractmethod
    async def generate_with_history(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """יצירת תשובה עם היסטוריית שיחה."""
        pass

    def _extract_json(self, text: str) -> str:
        """חילוץ JSON מתוך תשובה שעלולה להכיל טקסט נוסף."""
        text = text.strip()

        # אם מתחיל ב-JSON, מחפש סוגריים תואמים
        if text.startswith("{"):
            depth = 0
            for i, char in enumerate(text):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[:i+1]
            return text

        # חיפוש בלוק JSON ב-markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # חיפוש { ראשון ו-} אחרון
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]

        return text


class ClaudeLLMClient(BaseLLMClient):
    """
    LLM Client עבור Claude (Anthropic).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        # ולידציה של API key
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY לא הוגדר")

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.model = model or settings.CLAUDE_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """יצירת תשובה טקסטית מ-Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if temperature is not None:
            kwargs["temperature"] = temperature
        else:
            kwargs["temperature"] = self.temperature

        logger.debug(f"קורא ל-Claude API עם מודל: {self.model}")

        response = await self.client.messages.create(**kwargs)

        content = response.content[0].text
        logger.debug(f"התקבלה תשובה: {len(content)} תווים")

        return content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> T:
        """יצירת תשובה מובנית מ-Claude."""
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

        structured_prompt = f"""{prompt}

You MUST respond with a valid JSON object that conforms to this schema:

```json
{schema_str}
```

IMPORTANT: Respond ONLY with the JSON object, no additional text or markdown.
"""

        base_system = system_prompt or ""
        full_system = f"""{base_system}

You are a helpful AI assistant that responds in structured JSON format.
Always respond with valid JSON that matches the requested schema.
Do not include any text before or after the JSON object.
Use Hebrew for text content where appropriate."""

        response_text = await self.generate(
            prompt=structured_prompt,
            system_prompt=full_system,
            max_tokens=max_tokens,
            temperature=0.3
        )

        try:
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)
            return response_model.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"נכשל בפרסור JSON: {e}")
            logger.error(f"התשובה הייתה: {response_text[:500]}")
            raise ValueError(f"תשובת LLM אינה JSON תקין: {e}")
        except Exception as e:
            logger.error(f"נכשל באימות מול המודל: {e}")
            raise

    async def generate_with_history(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """יצירת תשובה עם היסטוריה מ-Claude."""
        claude_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"]:
                claude_messages.append({"role": role, "content": content})

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": claude_messages,
            "temperature": self.temperature
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)
        return response.content[0].text


class GeminiLLMClient(BaseLLMClient):
    """
    LLM Client עבור Gemini (Google).
    משתמש ב-Client class לתמיכה ב-API key per-instance.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        # ייבוא דינמי כדי שלא תהיה שגיאה אם החבילה לא מותקנת
        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.types = types
        except ImportError:
            raise ImportError(
                "חבילת google-genai לא מותקנת. "
                "התקן אותה עם: pip install google-genai"
            )

        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY לא הוגדר")

        # יצירת Client instance עם API key ספציפי (לא גלובלי)
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model or settings.GEMINI_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """יצירת תשובה טקסטית מ-Gemini."""
        # הגדרות יצירה
        config = self.types.GenerateContentConfig(
            max_output_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            system_instruction=system_prompt
        )

        logger.debug(f"קורא ל-Gemini API עם מודל: {self.model_name}")

        # קריאה אסינכרונית ל-API
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )

        content = response.text
        logger.debug(f"התקבלה תשובה: {len(content)} תווים")

        return content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> T:
        """יצירת תשובה מובנית מ-Gemini."""
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

        structured_prompt = f"""{prompt}

You MUST respond with a valid JSON object that conforms to this schema:

```json
{schema_str}
```

IMPORTANT: Respond ONLY with the JSON object, no additional text or markdown.
"""

        base_system = system_prompt or ""
        full_system = f"""{base_system}

You are a helpful AI assistant that responds in structured JSON format.
Always respond with valid JSON that matches the requested schema.
Do not include any text before or after the JSON object.
Use Hebrew for text content where appropriate."""

        response_text = await self.generate(
            prompt=structured_prompt,
            system_prompt=full_system,
            max_tokens=max_tokens,
            temperature=0.3
        )

        try:
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)
            return response_model.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"נכשל בפרסור JSON: {e}")
            logger.error(f"התשובה הייתה: {response_text[:500]}")
            raise ValueError(f"תשובת LLM אינה JSON תקין: {e}")
        except Exception as e:
            logger.error(f"נכשל באימות מול המודל: {e}")
            raise

    async def generate_with_history(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """יצירת תשובה עם היסטוריה מ-Gemini."""
        # המרת היסטוריה לפורמט של Gemini (רק roles תקינים)
        gemini_contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # מסנן רק roles תקינים (כמו ClaudeLLMClient)
            if role not in ["user", "assistant"]:
                continue
            # Gemini משתמש ב-"user" ו-"model"
            gemini_role = "model" if role == "assistant" else "user"
            gemini_contents.append(
                self.types.Content(role=gemini_role, parts=[self.types.Part(text=content)])
            )

        # הגדרות יצירה
        config = self.types.GenerateContentConfig(
            max_output_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            system_instruction=system_prompt
        )

        # קריאה אסינכרונית עם היסטוריה
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=gemini_contents,
            config=config
        )

        return response.text


# Alias לתאימות לאחור
LLMClient = ClaudeLLMClient


def create_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """
    Factory function ליצירת LLM client לפי הספק הנבחר.

    Args:
        provider: "claude" או "gemini". אם לא צוין, נקרא מההגדרות.

    Returns:
        instance של BaseLLMClient
    """
    provider = provider or settings.LLM_PROVIDER

    if provider.lower() == "gemini":
        logger.info("יוצר Gemini LLM client")
        return GeminiLLMClient(
            api_key=settings.GOOGLE_API_KEY,
            model=settings.GEMINI_MODEL,
            max_tokens=settings.GEMINI_MAX_TOKENS,
            temperature=settings.GEMINI_TEMPERATURE
        )
    else:
        # ברירת מחדל: Claude
        logger.info("יוצר Claude LLM client")
        return ClaudeLLMClient(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            temperature=settings.CLAUDE_TEMPERATURE
        )
