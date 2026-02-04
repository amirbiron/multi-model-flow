"""
Architect Agent - Feasibility Node
===================================
Assesses the feasibility of the proposed architecture
in terms of cost, complexity, and team fit.
"""
import logging
from typing import Tuple, List

from ..state import (
    ProjectContext, FeasibilityAssessment, CostBand, Priority
)
from ...llm.client import LLMClient
from ...llm.prompts import FEASIBILITY_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def feasibility_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str]:
    """
    Feasibility node - assesses cost, complexity, and team fit.

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message)
    """
    logger.info(f"[{ctx.session_id}] Running feasibility node")
    ctx.current_node = "assess_feasibility"

    if not ctx.proposed_architecture:
        reply = "⚠️ לא נבחר Pattern עדיין. חוזר לשלב הקודם."
        ctx.add_message("assistant", reply)
        return ctx, reply

    # Generate feasibility assessment
    assessment = await _assess_feasibility(ctx, llm)
    ctx.feasibility = assessment

    # Check for warnings
    warnings = _check_constraint_alignment(ctx)

    # Build reply
    reply = _build_feasibility_reply(assessment, warnings)
    ctx.add_message("assistant", reply)

    # Update confidence based on feasibility
    if not warnings:
        ctx.confidence_score = min(ctx.confidence_score + 0.1, 0.95)
    elif len(warnings) > 2:
        ctx.confidence_score = max(ctx.confidence_score - 0.1, 0.4)

    logger.info(
        f"[{ctx.session_id}] Feasibility: cost={assessment.cost_band}, "
        f"complexity={assessment.ops_complexity}, warnings={len(warnings)}"
    )

    return ctx, reply


async def _assess_feasibility(
    ctx: ProjectContext,
    llm: LLMClient
) -> FeasibilityAssessment:
    """Generate feasibility assessment using LLM."""

    pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else "unknown"

    tech_stack_str = "\n".join([
        f"- {comp.layer}: {comp.technology}"
        for comp in ctx.tech_stack
    ]) if ctx.tech_stack else "לא הוגדר"

    constraints_str = "\n".join([
        f"- [{c.type}] {c.description} (severity: {c.severity})"
        for c in ctx.constraints
    ]) if ctx.constraints else "אין"

    # הדרישות המקוריות - לבדיקת over-engineering
    requirements_str = "\n".join([
        f"- {r.description}"
        for r in ctx.requirements
    ]) if ctx.requirements else "לא צוינו"

    prompt = FEASIBILITY_PROMPT.format(
        pattern=pattern,
        tech_stack=tech_stack_str,
        constraints=constraints_str,
        original_requirements=requirements_str
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=FeasibilityAssessment,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"Feasibility assessment failed: {e}")
        # Return conservative estimate
        return FeasibilityAssessment(
            cost_band=CostBand.MEDIUM,
            ops_complexity=CostBand.MEDIUM,
            cost_drivers=["הערכה לא זמינה"],
            cost_reducers=["הערכה לא זמינה"],
            team_fit=True,
            time_estimate="לא ניתן להעריך",
            risks=["יש לבצע הערכה מפורטת יותר"]
        )


def _check_constraint_alignment(ctx: ProjectContext) -> List[str]:
    """Check if feasibility aligns with constraints."""
    warnings = []

    if not ctx.feasibility:
        return warnings

    for constraint in ctx.constraints:
        # Budget constraint vs cost band
        if constraint.type == "budget":
            if (ctx.feasibility.cost_band == CostBand.HIGH and
                constraint.severity in [Priority.HIGH, Priority.CRITICAL]):
                warnings.append(
                    "⚠️ העלות הצפויה גבוהה ביחס לאילוץ התקציב"
                )

        # Timeline constraint vs time estimate
        if constraint.type == "timeline":
            if ("חודש" in ctx.feasibility.time_estimate.lower() and
                "שבוע" in constraint.description.lower()):
                warnings.append(
                    "⚠️ הערכת הזמן ארוכה מאילוץ לוח הזמנים"
                )

        # Team constraint vs complexity
        if constraint.type == "team":
            if (ctx.feasibility.ops_complexity == CostBand.HIGH and
                not ctx.feasibility.team_fit):
                warnings.append(
                    "⚠️ המורכבות עשויה להיות גבוהה מדי ליכולות הצוות"
                )

    return warnings


def _build_feasibility_reply(
    assessment: FeasibilityAssessment,
    warnings: List[str]
) -> str:
    """Build the feasibility assessment reply."""

    # Cost band emoji/text mapping
    cost_display = {
        CostBand.LOW: ("🟢", "נמוכה (עד $500/חודש)"),
        CostBand.MEDIUM: ("🟡", "בינונית ($500-$5000/חודש)"),
        CostBand.HIGH: ("🔴", "גבוהה (מעל $5000/חודש)")
    }

    complexity_display = {
        CostBand.LOW: ("🟢", "נמוכה - קל לתחזק"),
        CostBand.MEDIUM: ("🟡", "בינונית - דורש ידע טכני"),
        CostBand.HIGH: ("🔴", "גבוהה - צריך DevOps מסור")
    }

    cost_emoji, cost_text = cost_display.get(
        assessment.cost_band, ("⚪", "לא ידוע")
    )
    comp_emoji, comp_text = complexity_display.get(
        assessment.ops_complexity, ("⚪", "לא ידוע")
    )

    team_fit_text = "✅ מתאים" if assessment.team_fit else "⚠️ עלול להיות מאתגר"

    parts = [
        "## 💰 הערכת היתכנות\n",
        f"**עלות משוערת:** {cost_emoji} {cost_text}",
        f"**מורכבות תפעולית:** {comp_emoji} {comp_text}",
        f"**התאמה לצוות:** {team_fit_text}",
        f"**הערכת זמן:** {assessment.time_estimate}",
        ""
    ]

    # Cost drivers
    if assessment.cost_drivers:
        parts.append("### 📈 מה מייקר:")
        for driver in assessment.cost_drivers:
            parts.append(f"  • {driver}")
        parts.append("")

    # Cost reducers
    if assessment.cost_reducers:
        parts.append("### 📉 מה מוזיל:")
        for reducer in assessment.cost_reducers:
            parts.append(f"  • {reducer}")
        parts.append("")

    # Risks
    if assessment.risks:
        parts.append("### ⚡ סיכונים לשים לב:")
        for risk in assessment.risks:
            parts.append(f"  • {risk}")
        parts.append("")

    # Warnings
    if warnings:
        parts.append("### ⚠️ התראות:")
        for warning in warnings:
            parts.append(f"  {warning}")
        parts.append("")
        parts.append("*ייתכן שכדאי לשקול מחדש את ההמלצה או לעדכן אילוצים.*")
    else:
        parts.append("✅ **אין התנגשויות עם האילוצים שהוגדרו.**")

    parts.append("\nממשיך ליצירת ה-Blueprint...")

    return "\n".join(parts)
