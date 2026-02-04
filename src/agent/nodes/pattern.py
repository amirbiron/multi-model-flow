"""
Architect Agent - Pattern Node
===============================
Selects architectural pattern using deterministic scoring
combined with LLM reasoning.

This is the core node that implements the Scoring + LLM hybrid approach.
"""
import logging
from typing import Tuple, List
from pydantic import BaseModel, Field

from ..state import (
    ProjectContext, ArchitecturalDecision, TechStackComponent,
    PatternSelection
)
from ...llm.client import LLMClient
from ...llm.prompts import (
    PATTERN_SELECTION_PROMPT, TECH_STACK_PROMPT, BASE_SYSTEM_PROMPT
)
from ...knowledge.patterns import PATTERNS, get_pattern
from ...knowledge.decision_matrix import (
    score_all_patterns, get_top_recommendations,
    convert_to_architectural_decisions, ScoredPattern
)

logger = logging.getLogger(__name__)


class TechStackResponse(BaseModel):
    """LLM response for tech stack recommendations."""
    recommendations: List[TechStackComponent]


async def pattern_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str]:
    """
    Pattern selection node - combines deterministic scoring with LLM judgment.

    The flow:
    1. Check for forced_pattern (from swap_option verdict)
    2. Score all patterns using the decision matrix (deterministic)
    3. Get top 3 candidates
    4. Use LLM to make final selection and provide justification
    5. Generate tech stack recommendations

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message)
    """
    logger.info(f"[{ctx.session_id}] Running pattern node")
    ctx.current_node = "pattern"

    # ========================================
    # STEP 0: Check for forced pattern (from swap_option)
    # ========================================
    forced_pattern = ctx.forced_pattern
    if forced_pattern:
        logger.info(f"Using forced pattern from swap_option: {forced_pattern}")
        # מנקה את forced_pattern אחרי שימוש כדי לא להשפיע על ריצות עתידיות
        ctx.forced_pattern = None

    # ========================================
    # STEP 1: Deterministic Scoring
    # ========================================
    logger.info("Step 1: Running deterministic scoring...")

    all_scored = score_all_patterns(
        priorities=ctx.priority_ranking,
        constraints=ctx.constraints,
        profile=ctx.decision_profile
    )

    top_candidates = get_top_recommendations(
        priorities=ctx.priority_ranking,
        constraints=ctx.constraints,
        profile=ctx.decision_profile,
        top_n=3
    )

    if not top_candidates:
        # Fallback if no viable patterns
        top_candidates = all_scored[:3]

    # אם יש forced_pattern, מוודא שהוא בראש הרשימה
    if forced_pattern:
        # מחפש את ה-forced_pattern ברשימה
        forced_in_list = next(
            (sp for sp in all_scored if sp.name == forced_pattern),
            None
        )
        if forced_in_list:
            # מסיר אותו מהמיקום הנוכחי ומוסיף בהתחלה
            top_candidates = [forced_in_list] + [
                c for c in top_candidates if c.name != forced_pattern
            ][:2]
            logger.info(f"Forced pattern {forced_pattern} moved to top of candidates")
        else:
            logger.warning(f"Forced pattern {forced_pattern} not found in patterns list")

    logger.info(
        f"Top candidates: {[(c.name, c.score) for c in top_candidates]}"
    )

    # ========================================
    # STEP 2: LLM Selection & Justification
    # ========================================
    logger.info("Step 2: LLM selection...")

    llm_selection = await _get_llm_selection(ctx, llm, top_candidates)

    # אם יש forced_pattern, מאלצים את הבחירה בו
    if forced_pattern:
        llm_selection.recommended_pattern = forced_pattern
        llm_selection.recommendation = (
            f"נבחר {forced_pattern} לפי הנחיית המערכת (swap_option). " +
            llm_selection.recommendation
        )
        logger.info(f"Forced LLM selection to: {forced_pattern}")

    # ========================================
    # STEP 3: Update Context with Decisions
    # ========================================

    # Convert to ArchitecturalDecision objects
    ctx.shortlist = convert_to_architectural_decisions(top_candidates)

    # Set the recommended pattern
    recommended_name = llm_selection.recommended_pattern.lower().replace(" ", "_")

    # Find the recommended pattern in shortlist
    ctx.proposed_architecture = None
    for decision in ctx.shortlist:
        if decision.pattern.lower() == recommended_name:
            ctx.proposed_architecture = decision
            # Add LLM justification
            ctx.proposed_architecture.justification = (
                llm_selection.justifications.get(decision.pattern, "") +
                "\n\n" + llm_selection.recommendation
            )
            break

    # Fallback to highest scored if LLM recommendation not found
    if not ctx.proposed_architecture and ctx.shortlist:
        ctx.proposed_architecture = ctx.shortlist[0]

    # ========================================
    # STEP 4: Tech Stack Recommendations
    # ========================================
    logger.info("Step 4: Generating tech stack...")

    ctx.tech_stack = await _generate_tech_stack(ctx, llm)

    # ========================================
    # STEP 5: Build Reply
    # ========================================

    reply = _build_pattern_reply(ctx, top_candidates, llm_selection)
    ctx.add_message("assistant", reply)

    # Bump confidence after successful pattern selection
    ctx.confidence_score = max(ctx.confidence_score, 0.6)

    return ctx, reply


async def _get_llm_selection(
    ctx: ProjectContext,
    llm: LLMClient,
    candidates: List[ScoredPattern]
) -> PatternSelection:
    """Get LLM's selection and justification for patterns."""

    candidates_info = []
    for sp in candidates:
        pattern_data = get_pattern(sp.name)
        candidates_info.append({
            "name": sp.name,
            "score": sp.score,
            "pros": pattern_data.get("pros", [])[:3],
            "cons": pattern_data.get("cons", [])[:3],
            "breakdown": sp.breakdown
        })

    # Build context summary (exclude conversation history)
    context_summary = {
        "project_name": ctx.project_name,
        "requirements_count": len(ctx.requirements),
        "constraints": [c.model_dump() for c in ctx.constraints],
        "decision_profile": ctx.decision_profile.value if ctx.decision_profile else None,
        "priority_weights": ctx.get_priority_weights(),
        "resolved_conflicts": [
            c.chosen_compromise for c in ctx.conflicts if c.resolved
        ]
    }

    prompt = PATTERN_SELECTION_PROMPT.format(
        candidates=candidates_info,
        context=context_summary
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=PatternSelection,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"LLM pattern selection failed: {e}")
        # Fallback to highest scored
        top = candidates[0] if candidates else None
        return PatternSelection(
            recommended_pattern=top.name if top else "monolith",
            justifications={top.name: top.reasoning} if top else {},
            recommendation="נבחר על בסיס הניקוד הגבוה ביותר"
        )


async def _generate_tech_stack(
    ctx: ProjectContext,
    llm: LLMClient
) -> List[TechStackComponent]:
    """Generate tech stack recommendations based on chosen pattern."""

    if not ctx.proposed_architecture:
        return []

    pattern = ctx.proposed_architecture.pattern
    pattern_data = get_pattern(pattern)

    # Get pattern's built-in recommendations as base
    base_recommendations = pattern_data.get("tech_recommendations", {})

    # Build requirements summary
    requirements_summary = "\n".join([
        f"- {r.description}" for r in ctx.requirements[:10]
    ])

    constraints_summary = "\n".join([
        f"- [{c.type}] {c.description}" for c in ctx.constraints
    ])

    prompt = TECH_STACK_PROMPT.format(
        pattern=pattern,
        requirements=requirements_summary or "לא צוינו",
        constraints=constraints_summary or "לא צוינו",
        preferences="לא צוינו"  # TODO: extract from requirements
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=TechStackResponse,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response.recommendations
    except Exception as e:
        logger.warning(f"Tech stack generation failed: {e}")
        # Return basic stack from pattern
        return _get_default_stack(pattern, base_recommendations)


def _get_default_stack(
    pattern: str,
    recommendations: dict
) -> List[TechStackComponent]:
    """Get default tech stack for a pattern."""
    stack = []

    # Backend
    if "backend" in recommendations:
        backends = recommendations["backend"]
        stack.append(TechStackComponent(
            layer="backend",
            technology=backends[0] if backends else "Python/FastAPI",
            reason="מומלץ עבור Pattern זה",
            alternatives=backends[1:3] if len(backends) > 1 else []
        ))

    # Database
    if "database" in recommendations:
        dbs = recommendations["database"]
        stack.append(TechStackComponent(
            layer="database",
            technology=dbs[0] if dbs else "PostgreSQL",
            reason="בחירה נפוצה ויציבה",
            alternatives=dbs[1:3] if len(dbs) > 1 else []
        ))

    # Deployment
    if "deployment" in recommendations:
        deploys = recommendations["deployment"]
        stack.append(TechStackComponent(
            layer="cloud",
            technology=deploys[0] if deploys else "Render",
            reason="פשוט לפריסה",
            alternatives=deploys[1:3] if len(deploys) > 1 else []
        ))

    return stack


def _build_pattern_reply(
    ctx: ProjectContext,
    candidates: List[ScoredPattern],
    selection: PatternSelection
) -> str:
    """Build the pattern recommendation reply."""

    parts = ["## 🏗️ המלצת ארכיטקטורה\n"]

    # Scoring results
    parts.append("### 📊 תוצאות הניקוד:\n")
    parts.append("| Pattern | ניקוד | סטטוס |")
    parts.append("|---------|-------|-------|")

    for sp in candidates:
        is_selected = sp.name == selection.recommended_pattern.lower().replace(" ", "_")
        status = "✅ **מומלץ**" if is_selected else "אלטרנטיבה"
        pattern_data = get_pattern(sp.name)
        name = pattern_data.get("name", sp.name)
        parts.append(f"| {name} | {sp.score:.0f}/100 | {status} |")

    parts.append("")

    # Selected pattern details
    if ctx.proposed_architecture:
        pattern_data = get_pattern(ctx.proposed_architecture.pattern)
        parts.append(f"### 🎯 הבחירה: **{pattern_data.get('name', ctx.proposed_architecture.pattern)}**\n")
        parts.append(selection.recommendation)
        parts.append("")

        # Trade-offs
        if ctx.proposed_architecture.trade_offs:
            parts.append("**Trade-offs להיות מודעים אליהם:**")
            for to in ctx.proposed_architecture.trade_offs[:4]:
                parts.append(f"  • {to}")
            parts.append("")

    # Tech Stack
    if ctx.tech_stack:
        parts.append("### 🛠️ Tech Stack מומלץ:\n")
        for comp in ctx.tech_stack:
            layer_names = {
                "backend": "🔧 Backend",
                "frontend": "🎨 Frontend",
                "database": "🗄️ Database",
                "cache": "⚡ Cache",
                "cloud": "☁️ Deployment",
                "monitoring": "📊 Monitoring",
                "auth": "🔐 Auth"
            }
            layer_name = layer_names.get(comp.layer, comp.layer)
            parts.append(f"**{layer_name}:** {comp.technology}")
            parts.append(f"  _{comp.reason}_")
            if comp.alternatives:
                parts.append(f"  חלופות: {', '.join(comp.alternatives)}")
            parts.append("")

    parts.append("\nממשיך לבדיקת היתכנות...")

    return "\n".join(parts)
