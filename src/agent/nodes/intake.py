"""
Architect Agent - Intake Node
==============================
First node in the workflow. Collects initial project requirements
and generates clarifying questions.
"""
import logging
from typing import Tuple

from ..state import (
    ProjectContext, Requirement, Constraint, IntakeResponse,
    Priority
)
from ...llm.client import LLMClient
from ...llm.prompts import INTAKE_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def intake_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str]:
    """
    Intake node - analyzes initial user message and extracts structured info.

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message)
    """
    logger.info(f"[{ctx.session_id}] Running intake node")

    # Build prompt
    history_str = _format_history(ctx.conversation_history)
    prompt = INTAKE_PROMPT.format(
        user_message=ctx.initial_summary or "",
        history=history_str if history_str else "אין היסטוריה קודמת"
    )

    # Call LLM for structured response
    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=IntakeResponse,
            system_prompt=BASE_SYSTEM_PROMPT
        )

        # Update context
        ctx.project_name = response.project_name
        ctx.requirements.extend(response.requirements)
        ctx.constraints.extend(response.constraints)
        ctx.open_questions = response.questions[:5]  # Max 5 questions
        ctx.confidence_score = response.confidence
        ctx.current_node = "intake"

        # Build reply
        reply = _build_intake_reply(response)
        ctx.add_message("assistant", reply)

        logger.info(
            f"[{ctx.session_id}] Intake complete: "
            f"{len(ctx.requirements)} requirements, "
            f"{len(ctx.constraints)} constraints, "
            f"confidence: {ctx.confidence_score:.2f}"
        )

        return ctx, reply

    except Exception as e:
        logger.error(f"[{ctx.session_id}] Intake node failed: {e}")
        ctx.error_message = str(e)

        # Fallback: ask for clarification
        reply = """
## 🤔 צריך קצת יותר מידע

לא הצלחתי לנתח את התיאור במלואו. בבקשה ספר לי:

1. מה המוצר/שירות שאתה בונה?
2. מי קהל היעד?
3. מה הסדר גודל הצפוי? (משתמשים, תנועה)
4. יש לוח זמנים או תקציב מוגדר?
5. יש דרישות טכנולוגיות מיוחדות?
"""
        ctx.add_message("assistant", reply)
        ctx.open_questions = [
            "מה המוצר/שירות?",
            "מי קהל היעד?",
            "סדר גודל צפוי?",
            "לוח זמנים/תקציב?"
        ]

        return ctx, reply


def _format_history(history: list) -> str:
    """Format conversation history for prompt."""
    if not history:
        return ""

    formatted = []
    for msg in history[-10:]:  # Last 10 messages
        role = msg.get("role", "user")
        content = msg.get("content", "")
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


def _build_intake_reply(response: IntakeResponse) -> str:
    """Build a user-friendly reply from intake response."""
    parts = [
        f"## 📊 הבנתי - {response.project_name}\n",
        response.summary,
        ""
    ]

    # Show identified requirements summary
    if response.requirements:
        func_reqs = [r for r in response.requirements if r.category == "functional"]
        non_func_reqs = [r for r in response.requirements if r.category == "non_functional"]

        if func_reqs:
            parts.append(f"**דרישות פונקציונליות:** זיהיתי {len(func_reqs)} דרישות")
        if non_func_reqs:
            parts.append(f"**דרישות לא-פונקציונליות:** זיהיתי {len(non_func_reqs)} דרישות")
        parts.append("")

    # Show constraints if any
    if response.constraints:
        parts.append(f"**אילוצים שזיהיתי:** {len(response.constraints)}")
        for c in response.constraints[:3]:  # Show first 3
            severity_icon = {
                Priority.CRITICAL: "🔴",
                Priority.HIGH: "🟠",
                Priority.MEDIUM: "🟡",
                Priority.LOW: "🟢"
            }.get(c.severity, "⚪")
            parts.append(f"  {severity_icon} {c.description}")
        parts.append("")

    # Add questions
    if response.questions:
        parts.append("### ❓ שאלות להבהרה:\n")
        for i, q in enumerate(response.questions[:5], 1):
            parts.append(f"{i}. {q}")

    # Add confidence indicator
    confidence_text = _get_confidence_text(response.confidence)
    parts.append(f"\n*רמת הבנה: {confidence_text}*")

    return "\n".join(parts)


def _get_confidence_text(confidence: float) -> str:
    """Get Hebrew text for confidence level."""
    if confidence >= 0.8:
        return "גבוהה ✅"
    elif confidence >= 0.6:
        return "טובה 👍"
    elif confidence >= 0.4:
        return "בינונית - צריך עוד מידע"
    else:
        return "נמוכה - צריך הרבה יותר מידע"
