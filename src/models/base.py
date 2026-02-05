"""
Base class לכל המודלים
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelResponse:
    """תשובה מהמודל"""
    content: str  # התוכן בפורמט Markdown
    model_name: str  # שם המודל
    success: bool = True
    error: Optional[str] = None


class BaseModel(ABC):
    """
    Base class לכל מודלי ה-LLM.
    כל מודל חייב לממש את המתודה `generate`.
    """

    def __init__(self, api_key: str, model_id: str):
        self.api_key = api_key
        self.model_id = model_id

    @property
    @abstractmethod
    def name(self) -> str:
        """שם המודל להצגה"""
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> ModelResponse:
        """
        שולח prompt למודל ומחזיר תשובה בפורמט Markdown.

        Args:
            prompt: הפרומפט לשליחה

        Returns:
            ModelResponse עם התשובה בפורמט Markdown
        """
        pass

    def _build_chain_prompt(
        self,
        original_question: str,
        previous_responses: list[tuple[str, str]]
    ) -> str:
        """
        בונה prompt שכולל את השאלה המקורית + תשובות קודמות.

        Args:
            original_question: השאלה המקורית מהמשתמש
            previous_responses: רשימת tuples של (שם_מודל, תשובה)

        Returns:
            Prompt מלא לשליחה למודל
        """
        if not previous_responses:
            # מודל ראשון - רק השאלה
            return f"""אנא ענה על השאלה הבאה בפורמט Markdown מסודר:

## השאלה:
{original_question}

---

אנא תן תשובה מקיפה ומפורטת בפורמט Markdown."""

        # מודל שני ואילך - כולל תשובות קודמות
        responses_text = ""
        for i, (model_name, response) in enumerate(previous_responses, 1):
            responses_text += f"""
### תשובה {i} - {model_name}:
{response}

---
"""

        return f"""קיבלת שאלה שכבר נענתה על ידי מודלים אחרים.
המשימה שלך: לקרוא את התשובות הקודמות, ללמוד מהן, ולתת תשובה משודרגת שמשלבת את הרעיונות הטובים + תובנות חדשות משלך.

## השאלה המקורית:
{original_question}

---

## תשובות קודמות:
{responses_text}

---

## ההנחיות שלך:
1. קרא את כל התשובות הקודמות בעיון
2. זהה נקודות חזקות בכל תשובה
3. זהה פערים או נקודות שלא כוסו
4. תן תשובה מקיפה בפורמט Markdown שכוללת:
   - סיכום הנקודות החשובות מהתשובות הקודמות
   - תובנות ונקודות חדשות משלך
   - סיכום כולל ומסקנות

אנא כתוב את תשובתך בפורמט Markdown מסודר:"""
