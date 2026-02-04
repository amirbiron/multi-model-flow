"""
Architect Agent - Critic Node
==============================
Performs self-critique of the generated blueprint and decides
whether to approve or loop back to previous nodes.

This is the key node for the iterative refinement loop.
"""
import logging
from typing import Tuple, Optional

from ..state import ProjectContext, CriticAnalysis
from ...llm.client import LLMClient
from ...llm.prompts import CRITIC_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def critic_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str, Optional[str]]:
    """
    Critic node - reviews the blueprint and decides next action.

    This node can trigger loops back to:
    - deep_dive: if more info is needed
    - conflict: if new conflicts are detected
    - pattern: if the pattern choice seems wrong

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message, next_node_override)
        next_node_override is None if should proceed to END, otherwise
        the name of the node to loop back to.
    """
    logger.info(f"[{ctx.session_id}] Running critic node (iteration {ctx.iteration_count + 1})")
    ctx.current_node = "critic"
    ctx.iteration_count += 1

    # Run LLM critique
    analysis = await _run_critique(ctx, llm)

    # Update confidence and tracking
    ctx.confidence_score = analysis.confidence_score
    ctx.last_confidence_reason = analysis.low_confidence_reason

    # שומר את ה-pattern הנוכחי למעקב
    current_pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else None

    # Determine next action
    next_node = None

    if analysis.confidence_score < 0.7 and ctx.iteration_count < ctx.max_iterations:
        # בודק קודם אם הסיבה היא חוסר מידע - לא חוזרים אחורה, מחכים למשתמש
        if analysis.low_confidence_reason == "missing_info":
            ctx.waiting_for_user = True
            next_node = None
            reply = _build_missing_info_reply(analysis)

        # כלל 4: confidence בינוני (0.5-0.7) - יציאה עם assumptions, לא לופ
        elif analysis.confidence_score >= 0.5:
            logger.info(f"Confidence {analysis.confidence_score:.2f} is acceptable, ending with assumptions")
            next_node = None
            reply = _build_approval_reply(analysis)  # מסיימים עם מה שיש

        # כלל 5: אם עברנו יותר מ-2 revisions - מספיק
        elif ctx.revision_count >= 2:
            logger.info(f"Already revised {ctx.revision_count} times, ending")
            next_node = None
            reply = _build_max_iterations_reply(analysis)

        # כלל 6: אם ה-pattern לא השתנה - אין טעם לחזור
        elif current_pattern and current_pattern == ctx.last_pattern:
            logger.info("Pattern unchanged, no point in revising")
            next_node = None
            reply = _build_approval_reply(analysis)

        else:
            # Need to loop back
            next_node = _determine_loop_target(analysis)
            if next_node:  # רק אם באמת חוזרים אחורה
                ctx.revision_count += 1
                # מעדכן last_pattern רק אחרי שהוחלט לחזור אחורה
                ctx.last_pattern = current_pattern
            reply = _build_loop_reply(analysis, next_node)
    elif ctx.iteration_count >= ctx.max_iterations:
        # Max iterations reached
        reply = _build_max_iterations_reply(analysis)
    else:
        # Approved!
        reply = _build_approval_reply(analysis)

    ctx.add_message("assistant", reply)

    logger.info(
        f"[{ctx.session_id}] Critic result: confidence={analysis.confidence_score:.2f}, "
        f"recommendation={analysis.recommendation}, next_node={next_node}"
    )

    return ctx, reply, next_node


async def _run_critique(ctx: ProjectContext, llm: LLMClient) -> CriticAnalysis:
    """Run LLM critique on the blueprint."""

    blueprint_str = ""
    if ctx.blueprint:
        blueprint_str = f"""
Executive Summary: {ctx.blueprint.executive_summary[:500]}
ADRs: {len(ctx.blueprint.adrs)}
Roadmap Phases: {list(ctx.blueprint.roadmap.keys())}
"""

    priorities_str = ""
    if ctx.priority_ranking:
        priorities_str = ctx.priority_ranking.model_dump_json()
    elif ctx.decision_profile:
        priorities_str = f"Profile: {ctx.decision_profile.value}"

    constraints_str = "\n".join([
        f"- [{c.type}] {c.description}" for c in ctx.constraints
    ])

    feasibility_str = ""
    if ctx.feasibility:
        feasibility_str = f"""
Cost: {ctx.feasibility.cost_band}
Complexity: {ctx.feasibility.ops_complexity}
Team Fit: {ctx.feasibility.team_fit}
"""

    prompt = CRITIC_PROMPT.format(
        blueprint=blueprint_str or "לא נוצר",
        priorities=priorities_str or "לא הוגדרו",
        constraints=constraints_str or "אין",
        feasibility=feasibility_str or "לא הוערך"
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=CriticAnalysis,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"Critique failed: {e}")
        # Return conservative analysis
        return CriticAnalysis(
            confidence_score=0.6,
            strengths=["הושלם תהליך בסיסי"],
            weaknesses=["לא ניתן היה לבצע ביקורת מלאה"],
            recommendation="approve"
        )


def _determine_loop_target(analysis: CriticAnalysis) -> str:
    """Determine which node to loop back to."""

    recommendation = analysis.recommendation

    if recommendation == "need_info":
        return "deep_dive"
    elif recommendation == "resolve_conflicts":
        return "conflict"
    elif recommendation == "revise_pattern":
        return "pattern"

    # Default based on confidence and issues
    if analysis.missing_info:
        return "deep_dive"
    elif analysis.conflicts:
        return "conflict"
    else:
        return "pattern"


def _build_missing_info_reply(analysis: CriticAnalysis) -> str:
    """Build reply when missing info requires user input."""

    parts = [
        f"## ❓ נדרש מידע נוסף\n",
        f"**רמת ביטחון:** {analysis.confidence_score:.0%}\n",
        f"**סיבה:** חסר מידע קריטי להמשך התכנון\n",
    ]

    if analysis.missing_info:
        parts.append(f"\n**מה חסר:**\n{analysis.missing_info}\n")

    if analysis.weaknesses:
        parts.append("**נקודות שדורשות התייחסות:**")
        for w in analysis.weaknesses[:3]:
            parts.append(f"  • {w}")
        parts.append("")

    parts.append("אנא ספק את המידע הנדרש כדי שאוכל להמשיך בתכנון.")

    return "\n".join(parts)


def _build_loop_reply(analysis: CriticAnalysis, next_node: str) -> str:
    """Build reply for looping back."""

    node_descriptions = {
        "deep_dive": "לשאול שאלות נוספות",
        "conflict": "לפתור קונפליקטים",
        "pattern": "לשקול Pattern חלופי"
    }

    reason = ""
    if analysis.missing_info:
        reason = f"חסר מידע: {analysis.missing_info}"
    elif analysis.conflicts:
        reason = f"קונפליקטים: {', '.join(analysis.conflicts[:2])}"
    elif analysis.weaknesses:
        reason = f"נקודות לשיפור: {analysis.weaknesses[0]}"

    parts = [
        f"## 🔄 ביקורת עצמית - חוזר לשלב קודם\n",
        f"**רמת ביטחון:** {analysis.confidence_score:.0%} (מתחת לסף 70%)\n",
        f"**סיבה:** {reason}\n",
        f"**פעולה:** {node_descriptions.get(next_node, next_node)}\n",
    ]

    if analysis.weaknesses:
        parts.append("**נקודות לטיפול:**")
        for w in analysis.weaknesses[:3]:
            parts.append(f"  • {w}")

    return "\n".join(parts)


def _build_approval_reply(analysis: CriticAnalysis) -> str:
    """Build reply for successful approval."""

    parts = [
        f"## ✅ ביקורת עברה בהצלחה!\n",
        f"**רמת ביטחון:** {analysis.confidence_score:.0%}\n",
    ]

    if analysis.strengths:
        parts.append("**נקודות חוזק:**")
        for s in analysis.strengths[:4]:
            parts.append(f"  ✓ {s}")
        parts.append("")

    if analysis.weaknesses:
        parts.append("**נקודות לשים לב (לא חוסמות):**")
        for w in analysis.weaknesses[:2]:
            parts.append(f"  • {w}")
        parts.append("")

    parts.append("---")
    parts.append("**ה-Blueprint מוכן!** 🎉")
    parts.append("אפשר להתחיל במימוש לפי ה-Roadmap שהוגדר.")

    return "\n".join(parts)


def _build_max_iterations_reply(analysis: CriticAnalysis) -> str:
    """Build reply when max iterations reached."""

    parts = [
        "## ⚠️ הגעתי למקסימום איטרציות\n",
        f"**רמת ביטחון סופית:** {analysis.confidence_score:.0%}\n",
        "מציג את התוצאה הטובה ביותר שיש לי.\n",
    ]

    if analysis.weaknesses:
        parts.append("**נקודות שעדיין דורשות תשומת לב:**")
        for w in analysis.weaknesses:
            parts.append(f"  ⚠️ {w}")
        parts.append("")

    parts.append("---")
    parts.append("**המלצה:** לסקור את ה-Blueprint עם הצוות לפני מימוש.")

    return "\n".join(parts)


def route_from_critic(ctx: ProjectContext) -> str:
    """
    Routing function for LangGraph conditional edge.
    Determines next node based on context state.

    לוגיקה חדשה למניעת לופים:
    1. confidence >= 0.7 -> יציאה רגילה
    2. 0.5 <= confidence < 0.7 -> יציאה עם assumptions/risks
    3. confidence < 0.5 -> רק אם יש פעולה ספציפית שיכולה לעזור

    Returns:
        Node name to transition to, or "end" to finish
    """
    # כלל 1: אם סיימנו - יוצאים
    if ctx.is_done():
        return "end"

    # כלל 2: הגבלת איטרציות
    if ctx.iteration_count >= ctx.max_iterations:
        logger.info(f"Reached max iterations ({ctx.max_iterations}), ending")
        return "end"

    # כלל 3: confidence גבוה - יציאה רגילה
    if ctx.confidence_score >= 0.7:
        return "end"

    # כלל 4: confidence בינוני (0.5-0.7) - יציאה עם assumptions
    # לא חוזרים אחורה בלופ! מסיימים עם הסתייגויות
    if ctx.confidence_score >= 0.5:
        logger.info(f"Confidence {ctx.confidence_score:.2f} is acceptable, ending with assumptions")
        return "end"

    # כלל 5: confidence נמוך (<0.5) - בודקים אם יש מה לעשות
    reason = ctx.last_confidence_reason

    # אם הסיבה היא חוסר מידע - כבר טופל ב-critic_node (waiting_for_user=True)
    if reason == "missing_info":
        logger.info("Low confidence due to missing info, need user input")
        return "end"

    # אם עברנו יותר מ-2 revisions - מספיק, מסיימים עם מה שיש
    if ctx.revision_count >= 2:
        logger.info(f"Already revised {ctx.revision_count} times, ending with current state")
        return "end"

    # אם יש conflicts לא פתורים - נסה לפתור אותם (פעם אחת)
    if ctx.has_unresolved_conflicts() and ctx.revision_count < 1:
        logger.info("Routing to conflict resolution")
        return "conflict"

    # אם ה-pattern לא השתנה מהפעם הקודמת - אין טעם לחזור
    current_pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else None
    if current_pattern and current_pattern == ctx.last_pattern:
        logger.info("Pattern unchanged, no point in revising again, ending")
        return "end"

    # אחרת - נסה deep_dive אחד נוסף (פעם אחת)
    if ctx.revision_count < 1:
        logger.info("Routing to deep_dive for more info")
        return "deep_dive"

    # ברירת מחדל - מסיימים
    logger.info("No actionable improvement possible, ending")
    return "end"
