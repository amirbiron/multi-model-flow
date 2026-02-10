"""
הגדרות הפרויקט וניהול API Keys
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelConfig:
    """הגדרות למודל בודד"""
    name: str
    api_key: Optional[str]
    model_id: str
    enabled: bool = True


@dataclass
class Config:
    """הגדרות הפרויקט"""

    # Claude
    claude_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-20250514"

    # Gemini
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3-pro-preview"

    # OpenAI (GPT)
    openai_api_key: Optional[str] = None
    gpt_model: str = "gpt-4o"

    # Mistral
    mistral_api_key: Optional[str] = None
    mistral_model: str = "mistral-large-latest"

    # Grok (xAI)
    grok_api_key: Optional[str] = None
    grok_model: str = "grok-2-latest"

    # DeepSeek
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-reasoner"

    # Perplexity
    perplexity_api_key: Optional[str] = None
    perplexity_model: str = "sonar-pro"

    # Qwen (Alibaba Cloud / DashScope)
    qwen_api_key: Optional[str] = None
    # ברירת מחדל לפי הבקשה - ניתן לשינוי בקוד/בעתיד דרך קונפיג
    qwen_model: str = "qwen3-max-2026-01-23"
    # DashScope OpenAI-Compatible base URL
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @classmethod
    def from_env(cls) -> "Config":
        """טעינת הגדרות ממשתני סביבה"""
        return cls(
            claude_api_key=os.getenv("ANTHROPIC_API_KEY"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            mistral_api_key=os.getenv("MISTRAL_API_KEY"),
            grok_api_key=os.getenv("GROK_API_KEY"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            perplexity_api_key=os.getenv("PERPLEXITY_API_KEY"),
            qwen_api_key=os.getenv("QWEN_API_KEY"),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
        )

    def get_available_models(self) -> list[str]:
        """מחזיר רשימת מודלים זמינים (עם API key)"""
        available = []
        if self.claude_api_key:
            available.append("claude")
        if self.gemini_api_key:
            available.append("gemini")
        if self.openai_api_key:
            available.append("gpt")
        if self.mistral_api_key:
            available.append("mistral")
        if self.grok_api_key:
            available.append("grok")
        if self.deepseek_api_key:
            available.append("deepseek")
        if self.perplexity_api_key:
            available.append("perplexity")
        if self.qwen_api_key:
            available.append("qwen")
        return available


# הגדרות גלובליות
config = Config.from_env()


# רשימת כל המודלים - מקור יחיד לאמת
# (id, display_name)
MODELS_REGISTRY = [
    ("claude", "Claude (Anthropic)"),
    ("gemini", "Gemini (Google)"),
    ("gpt", "GPT (OpenAI)"),
    ("mistral", "Mistral AI"),
    ("grok", "Grok (xAI)"),
    ("deepseek", "DeepSeek Reasoner"),
    ("perplexity", "Perplexity (Sonar)"),
    ("qwen", "Qwen (Alibaba Cloud)"),
]


def get_models_with_status() -> list[tuple[str, str, bool]]:
    """
    מחזיר רשימת כל המודלים עם סטטוס זמינות.
    Returns: list of (id, name, available)
    """
    api_keys = {
        "claude": config.claude_api_key,
        "gemini": config.gemini_api_key,
        "gpt": config.openai_api_key,
        "mistral": config.mistral_api_key,
        "grok": config.grok_api_key,
        "deepseek": config.deepseek_api_key,
        "perplexity": config.perplexity_api_key,
        "qwen": config.qwen_api_key,
    }

    return [
        (model_id, name, bool(api_keys.get(model_id)))
        for model_id, name in MODELS_REGISTRY
    ]
