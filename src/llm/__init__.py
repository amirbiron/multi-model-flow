"""
Architect Agent - LLM Package
==============================
Claude API client and prompts.
"""
from .client import LLMClient, create_llm_client
from .prompts import (
    BASE_SYSTEM_PROMPT,
    INTAKE_PROMPT,
    PRIORITY_PROMPT,
    CONFLICT_DETECTION_PROMPT,
    PATTERN_SELECTION_PROMPT,
    FEASIBILITY_PROMPT,
    CRITIC_PROMPT,
)

__all__ = [
    "LLMClient",
    "create_llm_client",
    "BASE_SYSTEM_PROMPT",
    "INTAKE_PROMPT",
    "PRIORITY_PROMPT",
    "CONFLICT_DETECTION_PROMPT",
    "PATTERN_SELECTION_PROMPT",
    "FEASIBILITY_PROMPT",
    "CRITIC_PROMPT",
]
