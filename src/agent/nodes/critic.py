"""
Architect Agent - Critic Node
==============================
Performs self-critique of the generated blueprint and decides
whether to approve or loop back to previous nodes.

This is the key node for the iterative refinement loop.

## לוגיקת Verdicts חדשה (מונעת לופים):
- accept: אישור סופי
- accept_with_notes: אישור עם הערות
- ask_user: חסר מידע - שואלים את המשתמש (לא חוזרים אחורה!)
- swap_option: טעות בבחירה - מחליפים pattern
"""
import logging
import json
from typing import Tuple, Optional, List

from ..state import ProjectContext, CriticAnalysis, CriticQuestion
from ...llm.client import LLMClient
from ...llm.prompts import CRITIC_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def critic_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str, Optional[str], Optional[List[CriticQuestion]]]:
    """
    Critic node - reviews the blueprint and decides next action based on verdict.

    ## לוגיקת Verdicts (מונעת לופים):
    - accept: סיום רגיל
    - accept_with_notes: סיום עם הסתייגויות
    - ask_user: שאילת שאלות למשתמש (לא לופ אחורה!)
    - swap_option: החלפת pattern (עם forced_pattern)

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message, next_node_override, questions_to_ask)
        - next_node_override: None=END, "ask_user", "pattern", etc.
        - questions_to_ask: שאלות לשאול את המשתמש (אם verdict=ask_user)
    """
    logger.info(f"[{ctx.session_id}] Running critic node (iteration {ctx.iteration_count + 1})")
    ctx.current_node = "critic"
    ctx.iteration_count += 1

    # מסמן שהמידע הנוכחי נוצל
    ctx.mark_info_used()

    # Run LLM critique
    analysis = await _run_critique(ctx, llm)

    # Update confidence and tracking
    ctx.confidence_score = analysis.confidence_score
    ctx.last_confidence_reason = analysis.low_confidence_reason

    # שומר את ה-pattern הנוכחי למעקב
    current_pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else None

    # Determine next action based on VERDICT (not just confidence)
    next_node = None
    questions_to_ask = None

    # בלם לופים - אחרי 2 איטרציות לא חוזרים פנימה עוד פעם בלי מידע חדש
    if ctx.iteration_count >= 2 and not ctx.has_new_info():
        logger.info(f"Iteration {ctx.iteration_count} without new info, forcing end")
        analysis.verdict = "accept_with_notes"

    # לוגיקת Verdict
    if analysis.verdict == "ask_user":
        # verdict=ask_user: שואלים את המשתמש במקום לחזור אחורה
        logger.info("Verdict: ask_user - need more info from user")
        ctx.waiting_for_user = True
        next_node = "ask_user"
        questions_to_ask = analysis.questions_to_ask
        reply = _build_ask_user_reply(analysis)

    elif analysis.verdict == "swap_option":
        # verdict=swap_option: מחליפים pattern
        if ctx.revision_count >= 2:
            # כבר עשינו 2 החלפות, מספיק
            logger.info("Already swapped 2 times, ending with current")
            next_node = None
            reply = _build_approval_reply(analysis)
        elif analysis.swap_to and analysis.swap_to.pattern:
            # יש pattern חלופי - מגדירים forced_pattern ועוברים ל-pattern node
            logger.info(f"Verdict: swap_option - switching to {analysis.swap_to.pattern}")
            ctx.forced_pattern = analysis.swap_to.pattern
            ctx.revision_count += 1
            ctx.last_pattern = current_pattern
            next_node = "pattern"
            reply = _build_swap_reply(analysis)
        else:
            # אין pattern חלופי - מסיימים עם מה שיש
            logger.info("Verdict: swap_option but no alternative specified, ending")
            next_node = None
            reply = _build_approval_reply(analysis)

    elif analysis.verdict == "accept_with_notes":
        # verdict=accept_with_notes: מסיימים עם הסתייגויות
        logger.info(f"Verdict: accept_with_notes (confidence={analysis.confidence_score:.2f})")
        next_node = None
        reply = _build_approval_with_notes_reply(analysis)

    else:  # accept
        # verdict=accept: אישור מלא
        logger.info(f"Verdict: accept (confidence={analysis.confidence_score:.2f})")
        next_node = None
        reply = _build_approval_reply(analysis)

    ctx.add_message("assistant", reply)

    logger.info(
        f"[{ctx.session_id}] Critic result: verdict={analysis.verdict}, "
        f"confidence={analysis.confidence_score:.2f}, next_node={next_node}"
    )

    return ctx, reply, next_node, questions_to_ask


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

    # הוספת שאלות שכבר נשאלו ועובדות שנאספו
    asked_questions_str = "\n".join([f"- {q}" for q in ctx.asked_questions]) if ctx.asked_questions else "אין"
    facts_str = json.dumps(ctx.facts, ensure_ascii=False, indent=2) if ctx.facts else "אין"

    prompt = CRITIC_PROMPT.format(
        blueprint=blueprint_str or "לא נוצר",
        priorities=priorities_str or "לא הוגדרו",
        constraints=constraints_str or "אין",
        feasibility=feasibility_str or "לא הוערך",
        asked_questions=asked_questions_str,
        facts=facts_str
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
        # Return conservative analysis with accept_with_notes
        return CriticAnalysis(
            confidence_score=0.6,
            strengths=["הושלם תהליך בסיסי"],
            weaknesses=["לא ניתן היה לבצע ביקורת מלאה"],
            verdict="accept_with_notes",
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
    """Build reply when missing info requires user input (legacy)."""

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


def _build_ask_user_reply(analysis: CriticAnalysis) -> str:
    """Build reply for ask_user verdict - שאילת שאלות למשתמש."""

    parts = [
        f"## ❓ צריך מידע נוסף לפני שממשיכים\n",
        f"**רמת ביטחון נוכחית:** {analysis.confidence_score:.0%}\n",
    ]

    if analysis.low_confidence_reason:
        reason_texts = {
            "missing_info": "חסר מידע קריטי",
            "conflicting_constraints": "יש אילוצים סותרים",
            "weak_justification": "הנימוקים לא מספיק חזקים",
            "wrong_choice": "ייתכן שיש בחירה טובה יותר",
            "other": "נדרש בירור נוסף"
        }
        parts.append(f"**סיבה:** {reason_texts.get(analysis.low_confidence_reason, analysis.low_confidence_reason)}\n")

    if analysis.questions_to_ask:
        parts.append("**שאלות שיעזרו לי לתת המלצה מדויקת יותר:**\n")
        for i, q in enumerate(analysis.questions_to_ask[:4], 1):
            parts.append(f"{i}. **{q.question}**")
            parts.append(f"   _למה זה חשוב: {q.why_it_matters}_\n")

    parts.append("---")
    parts.append("אפשר לענות בהודעה אחת או להגיד 'לא יודע' על שאלות שאין לך תשובה אליהן.")

    return "\n".join(parts)


def _build_swap_reply(analysis: CriticAnalysis) -> str:
    """Build reply for swap_option verdict - החלפת Pattern."""

    parts = [
        f"## 🔄 משנה את ההמלצה\n",
        f"**רמת ביטחון:** {analysis.confidence_score:.0%}\n",
    ]

    if analysis.swap_to:
        parts.append(f"**מחליף ל:** {analysis.swap_to.pattern}")
        if analysis.swap_to.why:
            parts.append(f"**סיבה:** {analysis.swap_to.why}\n")

    if analysis.weaknesses:
        parts.append("**בעיות בהמלצה הקודמת:**")
        for w in analysis.weaknesses[:3]:
            parts.append(f"  • {w}")
        parts.append("")

    parts.append("מריץ את התהליך מחדש עם ה-Pattern החדש...")

    return "\n".join(parts)


def _build_approval_with_notes_reply(analysis: CriticAnalysis) -> str:
    """Build reply for accept_with_notes verdict - אישור עם הסתייגויות."""

    parts = [
        f"## ✅ ביקורת עברה (עם הערות)\n",
        f"**רמת ביטחון:** {analysis.confidence_score:.0%}\n",
    ]

    if analysis.strengths:
        parts.append("**נקודות חוזק:**")
        for s in analysis.strengths[:3]:
            parts.append(f"  ✓ {s}")
        parts.append("")

    if analysis.weaknesses:
        parts.append("**הערות והסתייגויות (לא חוסמות):**")
        for w in analysis.weaknesses[:3]:
            parts.append(f"  ⚠️ {w}")
        parts.append("")

    if analysis.top_failure_modes:
        parts.append("**סיכונים עיקריים לשים לב אליהם:**")
        for fm in analysis.top_failure_modes[:3]:
            parts.append(f"  • {fm.failure} ({fm.severity})")
            parts.append(f"    מיטיגציה: {fm.mitigation}")
        parts.append("")

    parts.append("---")
    parts.append("**ה-Blueprint מוכן!** 🎉")
    parts.append("מומלץ לסקור את ההערות לפני מימוש.")

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
