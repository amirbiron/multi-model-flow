"""
Architect Agent - Ask User Node
================================
מציג שאלות למשתמש כאשר חסר מידע קריטי.
מעבד תשובות ומעדכן את ה-ProjectContext.

זהו ה-node שמונע לופים - במקום לחזור אחורה בלי מידע חדש,
הוא שואל את המשתמש שאלות ממוקדות.
"""
import logging
from typing import Tuple, List, Optional

from ..state import ProjectContext, CriticQuestion
from ...llm.client import LLMClient
from ...llm.prompts import ASK_USER_PROMPT, PARSE_USER_ANSWERS_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def ask_user_node(
    ctx: ProjectContext,
    llm: LLMClient,
    critic_questions: List[CriticQuestion] = None
) -> Tuple[ProjectContext, str, bool]:
    """
    Ask User Node - מציג שאלות למשתמש כשחסר מידע קריטי.

    במקום לחזור אחורה בלופ, ה-node הזה:
    1. לוקח את השאלות מה-Critic
    2. מסנן שאלות שכבר נשאלו
    3. מציג אותן בצורה ברורה למשתמש
    4. מסמן שממתינים לתשובה

    Args:
        ctx: Current project context
        llm: LLM client instance
        critic_questions: שאלות מה-Critic (אם לא סופק, לוקח מ-state)

    Returns:
        Tuple of (updated context, reply message, should_continue)
        - should_continue: True אם צריך להמשיך את הגרף (אין שאלות חדשות)
    """
    logger.info(f"[{ctx.session_id}] Running ask_user node")
    ctx.current_node = "ask_user"

    # לקיחת השאלות מה-Critic אם לא סופקו
    questions = critic_questions or []

    # סינון שאלות שכבר נשאלו
    filtered_questions = _filter_asked_questions(questions, ctx.asked_questions)

    if not filtered_questions:
        # אין שאלות חדשות לשאול - ממשיכים עם מה שיש
        logger.info("No new questions to ask, proceeding with current info")
        reply = _build_no_questions_reply()
        ctx.waiting_for_user = False
        # שומר את ההודעה להיסטוריה
        ctx.add_message("assistant", reply)
        # מחזיר should_continue=True כדי שהגרף ימשיך
        return ctx, reply, True

    # בניית הודעת השאלות
    reply = await _build_questions_message(ctx, llm, filtered_questions)

    # שמירת השאלות שנשאלו
    for q in filtered_questions:
        ctx.add_asked_question(q.question)

    # סימון שממתינים למשתמש
    ctx.waiting_for_user = True

    # שמירת השאלות הנוכחיות ב-state לשימוש כשתגיע תשובה
    ctx.conversation_history.append({
        "role": "system",
        "content": "pending_questions",
        "questions": [q.model_dump() for q in filtered_questions]
    })

    ctx.add_message("assistant", reply)

    logger.info(f"[{ctx.session_id}] Asked {len(filtered_questions)} questions, waiting for user")

    # מחזיר should_continue=False כדי שהגרף יעצור ויחכה למשתמש
    return ctx, reply, False


async def process_user_answers(
    ctx: ProjectContext,
    user_message: str,
    llm: LLMClient
) -> ProjectContext:
    """
    מעבד תשובות מהמשתמש ומעדכן את ה-facts ב-ProjectContext.

    Args:
        ctx: Current project context
        user_message: תשובת המשתמש
        llm: LLM client instance

    Returns:
        Updated ProjectContext with new facts
    """
    logger.info(f"[{ctx.session_id}] Processing user answers")

    # חיפוש השאלות שנשאלו מה-history
    pending_questions = _get_pending_questions(ctx)

    if not pending_questions:
        # אין שאלות ממתינות - לא מוסיפים הודעה כי continue_conversation כבר הוסיף אותה
        logger.warning("No pending questions found, skipping parse (message already in history)")
        return ctx

    # פירסור התשובות עם LLM
    parsed_answers = await _parse_answers_with_llm(
        ctx, llm, pending_questions, user_message
    )

    # עדכון ה-facts - תמיכה גם ב-ParsedAnswer models וגם ב-dicts
    for answer in parsed_answers:
        # תמיכה גם ב-model וגם ב-dict
        if hasattr(answer, 'normalized_value'):
            # זה ParsedAnswer model
            normalized_value = answer.normalized_value
            normalized_key = answer.normalized_key
            answer_id = answer.id
        else:
            # זה dict (מה-fallback)
            normalized_value = answer.get("normalized_value")
            normalized_key = answer.get("normalized_key", f"answer_{answer.get('id', 'unknown')}")
            answer_id = answer.get("id", "unknown")

        # בדיקה שהערך אינו None ואינו "unknown" (תומך ב-0, False, וכו')
        if normalized_value is not None and normalized_value != "unknown":
            ctx.add_fact(normalized_key, normalized_value)
            logger.info(f"Added fact: {normalized_key} = {normalized_value}")

    # עדכון info_version כבר קורה ב-add_fact
    ctx.waiting_for_user = False

    # הסרת השאלות הממתינות מה-history
    _remove_pending_questions(ctx)

    logger.info(f"[{ctx.session_id}] Processed answers, info_version now {ctx.info_version}")

    return ctx


def _filter_asked_questions(
    questions: List[CriticQuestion],
    asked_questions: List[str]
) -> List[CriticQuestion]:
    """מסנן שאלות שכבר נשאלו."""
    filtered = []
    for q in questions:
        # בדיקה אם השאלה או וריאציה שלה כבר נשאלה
        is_asked = any(
            _questions_similar(q.question, asked)
            for asked in asked_questions
        )
        if not is_asked:
            filtered.append(q)
    return filtered


def _questions_similar(q1: str, q2: str) -> bool:
    """בדיקה בסיסית אם שתי שאלות דומות."""
    # נורמליזציה בסיסית
    q1_normalized = q1.lower().strip().replace("?", "")
    q2_normalized = q2.lower().strip().replace("?", "")

    # בדיקת הכלה
    if q1_normalized in q2_normalized or q2_normalized in q1_normalized:
        return True

    # בדיקת מילות מפתח משותפות (threshold של 70%)
    words1 = set(q1_normalized.split())
    words2 = set(q2_normalized.split())
    if len(words1) > 0 and len(words2) > 0:
        common = len(words1 & words2)
        max_len = max(len(words1), len(words2))
        if common / max_len > 0.7:
            return True

    return False


async def _build_questions_message(
    ctx: ProjectContext,
    llm: LLMClient,
    questions: List[CriticQuestion]
) -> str:
    """בונה הודעת שאלות מעוצבת למשתמש."""

    # ננסה להשתמש ב-LLM לעיצוב השאלות
    try:
        questions_str = "\n".join([
            f"- שאלה: {q.question}\n  Impact: {q.impact}\n  למה חשוב: {q.why_it_matters}"
            for q in questions
        ])

        asked_str = "\n".join(ctx.asked_questions) if ctx.asked_questions else "אין"

        prompt = ASK_USER_PROMPT.format(
            critic_questions=questions_str,
            asked_questions=asked_str
        )

        response = await llm.generate(
            prompt=prompt,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"Failed to format questions with LLM: {e}")
        # fallback לפורמט בסיסי
        return _build_basic_questions_message(questions)


def _build_basic_questions_message(questions: List[CriticQuestion]) -> str:
    """בונה הודעת שאלות בסיסית (fallback)."""
    parts = [
        "## ❓ צריך מידע נוסף\n",
        "כדי לתת המלצה מדויקת יותר, אשמח לקבל תשובות לשאלות הבאות:\n"
    ]

    for i, q in enumerate(questions, 1):
        parts.append(f"\n**{i}. {q.question}**")
        parts.append(f"   _למה זה חשוב: {q.why_it_matters}_\n")

    parts.append("\n---")
    parts.append("אפשר לענות בהודעה אחת או להגיד 'לא יודע' על שאלות שאין לך תשובה אליהן.")

    return "\n".join(parts)


def _build_no_questions_reply() -> str:
    """הודעה כשאין שאלות חדשות לשאול."""
    return """## ℹ️ ממשיכים עם המידע הקיים

כל השאלות הרלוונטיות כבר נשאלו.
ממשיך עם המידע שיש לי כדי לתת את ההמלצה הטובה ביותר."""


def _get_pending_questions(ctx: ProjectContext) -> List[dict]:
    """מחלץ שאלות ממתינות מה-history."""
    for msg in reversed(ctx.conversation_history):
        if msg.get("role") == "system" and msg.get("content") == "pending_questions":
            return msg.get("questions", [])
    return []


def _remove_pending_questions(ctx: ProjectContext) -> None:
    """מסיר שאלות ממתינות מה-history."""
    ctx.conversation_history = [
        msg for msg in ctx.conversation_history
        if not (msg.get("role") == "system" and msg.get("content") == "pending_questions")
    ]


async def _parse_answers_with_llm(
    ctx: ProjectContext,
    llm: LLMClient,
    questions: List[dict],
    user_answers: str
) -> List[dict]:
    """מפרסר תשובות משתמש עם LLM."""
    try:
        questions_str = "\n".join([
            f"Q{i+1}: {q.get('question', '')}"
            for i, q in enumerate(questions)
        ])

        prompt = PARSE_USER_ANSWERS_PROMPT.format(
            questions=questions_str,
            user_answers=user_answers
        )

        # נשתמש ב-generate_structured אם אפשר
        from ..state import ParsedAnswers
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=ParsedAnswers,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response.answers
    except Exception as e:
        logger.warning(f"Failed to parse answers with LLM: {e}")
        # fallback - מחזיר תשובה גנרית
        return [{
            "id": "user_input",
            "value": user_answers,
            "normalized_key": "user_additional_info",
            "normalized_value": user_answers
        }]
