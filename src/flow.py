"""
Multi-Model Opinion Flow
זרימה לקבלת דעות מרובות ממודלים שונים
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .config import config
from .models import (
    BaseModel,
    ClaudeModel,
    GeminiModel,
    GPTModel,
    MistralModel,
    GrokModel,
    DeepSeekModel,
    PerplexityModel,
    QwenModel,
    ManusModel,
)
from .models.base import ModelResponse


@dataclass
class FlowResult:
    """תוצאת הזרימה"""
    question: str
    responses: list[ModelResponse] = field(default_factory=list)
    final_summary: str = ""


class MultiModelFlow:
    """
    זרימת Multi-Model Opinion Flow.

    הזרימה:
    1. שולח את השאלה למודל ראשון
    2. שולח את השאלה + תשובת מודל 1 למודל שני
    3. שולח את השאלה + תשובות 1+2 למודל שלישי
    4. וכן הלאה...

    כל מודל מקבל את התשובות הקודמות ובונה עליהן.
    """

    # סדר ברירת מחדל של המודלים
    DEFAULT_MODEL_ORDER = [
        "claude",
        "gemini",
        "gpt",
        "mistral",
        "grok",
        "deepseek",
        "perplexity",
        "qwen",
        "manus",
    ]

    def __init__(self, model_order: Optional[list[str]] = None):
        """
        אתחול הזרימה.

        Args:
            model_order: סדר המודלים (אופציונלי). אם לא מסופק, משתמש בסדר ברירת המחדל.
        """
        self.model_order = model_order or self.DEFAULT_MODEL_ORDER
        self.models: dict[str, BaseModel] = {}
        self._init_models()

    def _init_models(self) -> None:
        """אתחול המודלים הזמינים"""
        # Claude
        if config.claude_api_key:
            self.models["claude"] = ClaudeModel(
                api_key=config.claude_api_key,
                model_id=config.claude_model
            )

        # Gemini
        if config.gemini_api_key:
            self.models["gemini"] = GeminiModel(
                api_key=config.gemini_api_key,
                model_id=config.gemini_model
            )

        # GPT
        if config.openai_api_key:
            self.models["gpt"] = GPTModel(
                api_key=config.openai_api_key,
                model_id=config.gpt_model
            )

        # Mistral
        if config.mistral_api_key:
            self.models["mistral"] = MistralModel(
                api_key=config.mistral_api_key,
                model_id=config.mistral_model
            )

        # Grok
        if config.grok_api_key:
            self.models["grok"] = GrokModel(
                api_key=config.grok_api_key,
                model_id=config.grok_model
            )

        # DeepSeek
        if config.deepseek_api_key:
            self.models["deepseek"] = DeepSeekModel(
                api_key=config.deepseek_api_key,
                model_id=config.deepseek_model
            )

        # Perplexity
        if config.perplexity_api_key:
            self.models["perplexity"] = PerplexityModel(
                api_key=config.perplexity_api_key,
                model_id=config.perplexity_model
            )

        # Qwen (Alibaba Cloud / DashScope)
        if config.qwen_api_key:
            self.models["qwen"] = QwenModel(
                api_key=config.qwen_api_key,
                model_id=config.qwen_model,
                base_url=config.qwen_base_url
            )

        # Manus (OpenAI-compatible)
        if config.manus_api_key and config.manus_base_url:
            self.models["manus"] = ManusModel(
                api_key=config.manus_api_key,
                model_id=config.manus_model,
                base_url=config.manus_base_url
            )

    def get_available_models(self) -> list[str]:
        """מחזיר רשימת מודלים זמינים"""
        return [m for m in self.model_order if m in self.models]

    async def run(
        self,
        question: str,
        models_to_use: Optional[list[str]] = None,
        on_response: Optional[callable] = None
    ) -> FlowResult:
        """
        מריץ את הזרימה על השאלה.

        Args:
            question: השאלה/בעיה לשליחה
            models_to_use: רשימת מודלים לשימוש (אופציונלי)
            on_response: callback שנקרא אחרי כל תשובה (אופציונלי)

        Returns:
            FlowResult עם כל התשובות
        """
        result = FlowResult(question=question)

        # בחירת המודלים לשימוש
        if models_to_use:
            active_models = [m for m in models_to_use if m in self.models]
        else:
            active_models = self.get_available_models()

        if not active_models:
            raise ValueError("אין מודלים זמינים! וודא שהגדרת API keys.")

        # איסוף תשובות קודמות
        previous_responses: list[tuple[str, str]] = []

        # הרצת כל מודל בתור
        for model_name in active_models:
            model = self.models[model_name]

            # בניית הפרומפט עם התשובות הקודמות
            prompt = model._build_chain_prompt(question, previous_responses)

            # שליחה למודל
            response = await model.generate(prompt)
            result.responses.append(response)

            # עדכון רשימת התשובות הקודמות
            if response.success:
                previous_responses.append((model.name, response.content))

            # קריאה ל-callback אם קיים
            if on_response:
                on_response(response)

        # יצירת סיכום סופי
        result.final_summary = self._generate_summary(result)

        return result

    def _generate_summary(self, result: FlowResult) -> str:
        """יוצר סיכום סופי של כל התשובות"""
        successful_responses = [r for r in result.responses if r.success]

        if not successful_responses:
            return "# שגיאה\nלא התקבלו תשובות מהמודלים."

        summary = f"""# סיכום Multi-Model Opinion Flow

## השאלה המקורית:
{result.question}

---

## תשובות מהמודלים:

"""
        for i, response in enumerate(successful_responses, 1):
            summary += f"""### {i}. {response.model_name}

{response.content}

---

"""

        # הוספת מידע על שגיאות אם היו
        failed_responses = [r for r in result.responses if not r.success]
        if failed_responses:
            summary += "\n## מודלים שנכשלו:\n"
            for response in failed_responses:
                summary += f"- **{response.model_name}**: {response.error}\n"

        return summary


async def run_flow(
    question: str,
    models: Optional[list[str]] = None,
    verbose: bool = True
) -> FlowResult:
    """
    פונקציית עזר להרצת הזרימה.

    Args:
        question: השאלה לשליחה
        models: רשימת מודלים (אופציונלי)
        verbose: האם להדפיס התקדמות

    Returns:
        FlowResult עם התוצאות
    """
    flow = MultiModelFlow()

    available = flow.get_available_models()
    if verbose:
        print(f"מודלים זמינים: {', '.join(available)}")
        print("-" * 50)

    def on_response(response: ModelResponse):
        if verbose:
            status = "✅" if response.success else "❌"
            print(f"{status} {response.model_name}")

    result = await flow.run(
        question=question,
        models_to_use=models,
        on_response=on_response
    )

    return result
