"""
Architect Agent - Priority Node
================================
Aligns user priorities either through profile selection
or explicit ranking.
"""
import logging
from typing import Tuple

from ..state import (
    ProjectContext, DecisionProfile, PriorityRanking, ProfileDetection
)
from ...llm.client import LLMClient
from ...llm.prompts import PRIORITY_PROMPT, BASE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def priority_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str]:
    """
    Priority node - determines user's priorities for architecture decisions.

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message)
    """
    logger.info(f"[{ctx.session_id}] Running priority node")
    ctx.current_node = "priority"

    # If already has priorities, skip
    if ctx.decision_profile or ctx.priority_ranking:
        logger.info(f"[{ctx.session_id}] Priorities already set, skipping")
        return ctx, ""

    # Try to auto-detect profile from requirements
    detected = await _detect_profile(ctx, llm)

    if detected and detected.confidence > 0.75:
        # High confidence - suggest the detected profile
        ctx.decision_profile = detected.profile
        reply = _build_confirmation_reply(detected)
        ctx.add_message("assistant", reply)
        ctx.waiting_for_user = True
        logger.info(
            f"[{ctx.session_id}] Detected profile: {detected.profile} "
            f"(confidence: {detected.confidence:.2f})"
        )
        return ctx, reply

    # Low confidence - ask user to choose
    reply = _build_selection_reply()
    ctx.add_message("assistant", reply)
    ctx.waiting_for_user = True

    return ctx, reply


async def _detect_profile(
    ctx: ProjectContext,
    llm: LLMClient
) -> ProfileDetection:
    """Try to automatically detect the appropriate decision profile."""
    requirements_str = "\n".join([
        f"- [{r.category}] {r.description} (priority: {r.priority})"
        for r in ctx.requirements
    ])

    constraints_str = "\n".join([
        f"- [{c.type}] {c.description} (severity: {c.severity})"
        for c in ctx.constraints
    ])

    prompt = PRIORITY_PROMPT.format(
        requirements=requirements_str or "אין דרישות עדיין",
        constraints=constraints_str or "אין אילוצים"
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=ProfileDetection,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"Failed to detect profile: {e}")
        return ProfileDetection(
            profile=None,
            confidence=0.0,
            reasoning="לא הצלחתי לזהות פרופיל אוטומטית"
        )


def _build_confirmation_reply(detected: ProfileDetection) -> str:
    """Build reply asking for confirmation of detected profile."""
    profile_names = {
        DecisionProfile.MVP_FAST: "🚀 MVP_FAST - מהירות מעל הכל",
        DecisionProfile.COST_FIRST: "💰 COST_FIRST - חיסכון בעלויות",
        DecisionProfile.SCALE_FIRST: "📈 SCALE_FIRST - בניה לסקייל",
        DecisionProfile.SECURITY_FIRST: "🔒 SECURITY_FIRST - אבטחה קודמת",
    }

    profile_name = profile_names.get(
        detected.profile,
        str(detected.profile)
    )

    return f"""
## ⚖️ יישור עדיפויות

מהדרישות שתיארת, נראה שהעדיפות העיקרית שלך היא:

**{profile_name}**

{detected.reasoning}

**האם זה נכון?**
- ענה "כן" לאישור
- ענה "לא" כדי לבחור פרופיל אחר
- או דרג את העדיפויות בעצמך (1-5)
"""


def _build_selection_reply() -> str:
    """Build reply asking user to select a profile."""
    return """
## ⚖️ יישור עדיפויות

כדי להמליץ על הארכיטקטורה הנכונה, אני צריך להבין מה הכי חשוב לך.

**בחר פרופיל מוכן** (כתוב את המספר):

1. 🚀 **MVP_FAST** - מהירות מעל הכל, נצא לאוויר מהר
2. 💰 **COST_FIRST** - חיסכון בעלויות הוא המפתח
3. 📈 **SCALE_FIRST** - בונים לגדול, גם אם לוקח יותר זמן
4. 🔒 **SECURITY_FIRST** - אבטחה וציות קודמים לכל

**או דרג 1-5** (1=לא חשוב, 5=קריטי):
```
Time-to-market: ?
Cost: ?
Scale: ?
Reliability: ?
Security: ?
```
"""


def process_priority_response(ctx: ProjectContext, user_message: str) -> bool:
    """
    Process user's response to priority selection.

    Returns:
        True if priorities were successfully set, False otherwise
    """
    message = user_message.strip().lower()

    # Check for confirmation
    if message in ["כן", "yes", "נכון", "מאשר"]:
        return True  # Keep the detected profile

    # Check for profile selection by number
    profile_map = {
        "1": DecisionProfile.MVP_FAST,
        "2": DecisionProfile.COST_FIRST,
        "3": DecisionProfile.SCALE_FIRST,
        "4": DecisionProfile.SECURITY_FIRST,
    }

    if message in profile_map:
        ctx.decision_profile = profile_map[message]
        return True

    # Check for profile selection by name
    name_map = {
        "mvp": DecisionProfile.MVP_FAST,
        "fast": DecisionProfile.MVP_FAST,
        "cost": DecisionProfile.COST_FIRST,
        "scale": DecisionProfile.SCALE_FIRST,
        "security": DecisionProfile.SECURITY_FIRST,
    }

    for key, profile in name_map.items():
        if key in message:
            ctx.decision_profile = profile
            return True

    # Try to parse explicit ranking
    ranking = _parse_ranking(user_message)
    if ranking:
        ctx.priority_ranking = ranking
        ctx.decision_profile = None  # Clear profile if explicit ranking
        return True

    return False


def _parse_ranking(message: str) -> PriorityRanking | None:
    """Try to parse explicit 1-5 rankings from message."""
    import re

    # Look for patterns like "time: 5" or "cost: 3"
    patterns = {
        "time": r"time[^:]*:\s*(\d)",
        "cost": r"cost[^:]*:\s*(\d)",
        "scale": r"scale[^:]*:\s*(\d)",
        "reliability": r"reliab[^:]*:\s*(\d)",
        "security": r"secur[^:]*:\s*(\d)",
    }

    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 5:
                values[key] = val

    # Need at least 3 values to create ranking
    if len(values) >= 3:
        return PriorityRanking(
            time_to_market=values.get("time", 3),
            cost=values.get("cost", 3),
            scale=values.get("scale", 3),
            reliability=values.get("reliability", 3),
            security=values.get("security", 3)
        )

    return None
