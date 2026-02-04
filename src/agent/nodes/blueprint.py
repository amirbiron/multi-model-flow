"""
Architect Agent - Blueprint Node
=================================
Generates the final architecture blueprint document
including diagrams, ADRs, and roadmap.
"""
import logging
from typing import Tuple, List
from pydantic import BaseModel, Field

from ..state import ProjectContext, Blueprint, ADR
from ...llm.client import LLMClient
from ...llm.prompts import (
    BLUEPRINT_SUMMARY_PROMPT, MERMAID_PROMPT,
    ADR_PROMPT, ROADMAP_PROMPT, BASE_SYSTEM_PROMPT
)

logger = logging.getLogger(__name__)


class SummaryResponse(BaseModel):
    """LLM response for executive summary."""
    summary: str


class MermaidResponse(BaseModel):
    """LLM response for Mermaid diagram."""
    diagram: str


class ADRsResponse(BaseModel):
    """LLM response for ADRs."""
    adrs: List[ADR]


class RoadmapResponse(BaseModel):
    """LLM response for roadmap."""
    phases: dict  # phase_name -> list of tasks או מבנה מורכב יותר
    next_steps: List[str]
    assumptions: List[str]

    def get_normalized_phases(self) -> dict:
        """
        מנרמל את phases למבנה Dict[str, List[str]].
        מטפל במקרים שה-LLM מחזיר מבנה מורכב יותר.
        """
        normalized = {}
        for phase_key, phase_value in self.phases.items():
            if isinstance(phase_value, list):
                # מנרמל כל אלמנט ברשימה ל-string
                normalized[phase_key] = [str(item) for item in phase_value]
            elif isinstance(phase_value, dict):
                # מבנה מורכב - מחלץ את המשימות
                # משתמש ב-phase_key כדי למנוע דריסה של phases עם אותו name
                raw_tasks = phase_value.get("tasks", [])

                # יוצר רשימה חדשה כדי לא לשנות את המקור
                tasks = []

                if raw_tasks:
                    if isinstance(raw_tasks, str):
                        # אם tasks הוא string, מוסיף אותו כמשימה אחת
                        tasks.append(raw_tasks)
                    elif isinstance(raw_tasks, list):
                        # מנרמל את tasks ל-strings
                        tasks.extend([str(item) for item in raw_tasks])
                    else:
                        tasks.append(str(raw_tasks))
                else:
                    # אם אין tasks, מחפש שדות אחרים עם רשימות
                    for k, v in phase_value.items():
                        if k not in ("name", "description", "tasks") and v:
                            if isinstance(v, list):
                                # אם זו רשימה, מוסיף את האלמנטים שלה
                                tasks.extend([str(item) for item in v])
                            elif isinstance(v, str):
                                tasks.append(v)
                            else:
                                tasks.append(str(v))

                normalized[phase_key] = tasks if tasks else ["משימות לא הוגדרו"]
            else:
                # ערך פשוט - הופך לרשימה
                normalized[phase_key] = [str(phase_value)]
        return normalized


async def blueprint_node(
    ctx: ProjectContext,
    llm: LLMClient
) -> Tuple[ProjectContext, str]:
    """
    Blueprint node - generates the final architecture document.

    Args:
        ctx: Current project context
        llm: LLM client instance

    Returns:
        Tuple of (updated context, reply message)
    """
    logger.info(f"[{ctx.session_id}] Running blueprint node")
    ctx.current_node = "generate_blueprint"

    # Generate all blueprint components
    logger.info("Generating executive summary...")
    summary = await _generate_summary(ctx, llm)

    logger.info("Generating Mermaid diagram...")
    mermaid = await _generate_mermaid(ctx, llm)

    logger.info("Generating ADRs...")
    adrs = await _generate_adrs(ctx, llm)

    logger.info("Generating roadmap...")
    roadmap_data = await _generate_roadmap(ctx, llm)

    # Create Blueprint object
    ctx.blueprint = Blueprint(
        executive_summary=summary,
        mermaid_diagram=mermaid,
        adrs=adrs,
        roadmap=roadmap_data.get_normalized_phases(),
        next_steps=roadmap_data.next_steps,
        assumptions=roadmap_data.assumptions,
        unknowns=ctx.open_questions
    )

    # Build reply
    reply = _format_blueprint_as_markdown(ctx)
    ctx.add_message("assistant", reply)

    # High confidence after generating blueprint
    ctx.confidence_score = max(ctx.confidence_score, 0.75)

    logger.info(f"[{ctx.session_id}] Blueprint generated successfully")

    return ctx, reply


async def _generate_summary(ctx: ProjectContext, llm: LLMClient) -> str:
    """Generate executive summary."""
    pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else "N/A"
    tech_stack_str = ", ".join([
        f"{c.layer}:{c.technology}" for c in ctx.tech_stack[:5]
    ])
    priorities_str = (
        ctx.decision_profile.value if ctx.decision_profile
        else str(ctx.priority_ranking) if ctx.priority_ranking
        else "לא הוגדרו"
    )

    # Build process summary from conversation
    process_points = []
    if ctx.conflicts:
        resolved = sum(1 for c in ctx.conflicts if c.resolved)
        process_points.append(f"זוהו {len(ctx.conflicts)} קונפליקטים, {resolved} נפתרו")
    if ctx.shortlist:
        process_points.append(f"נבחנו {len(ctx.shortlist)} Patterns")

    # הדרישות המקוריות - למניעת המצאות!
    requirements_str = "\n".join([
        f"- {r.description}"
        for r in ctx.requirements
    ]) if ctx.requirements else "לא צוינו דרישות מפורשות"

    prompt = BLUEPRINT_SUMMARY_PROMPT.format(
        project_name=ctx.project_name or "הפרויקט",
        pattern=pattern,
        tech_stack=tech_stack_str,
        priorities=priorities_str,
        process_summary="\n".join(process_points) or "תהליך סטנדרטי",
        original_requirements=requirements_str
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=SummaryResponse,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response.summary
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        return f"Blueprint עבור {ctx.project_name or 'הפרויקט'} - מומלץ להשתמש ב-{pattern}"


async def _generate_mermaid(ctx: ProjectContext, llm: LLMClient) -> str:
    """Generate Mermaid diagram."""
    pattern = ctx.proposed_architecture.pattern if ctx.proposed_architecture else "monolith"
    tech_stack = [c.technology for c in ctx.tech_stack]

    prompt = MERMAID_PROMPT.format(
        pattern=pattern,
        tech_stack=tech_stack
    )

    try:
        response = await llm.generate(
            prompt=prompt,
            system_prompt="צור רק את קוד ה-Mermaid, בלי הסבר נוסף."
        )

        # Clean up response
        diagram = response.strip()

        # Remove markdown code blocks if present
        if diagram.startswith("```"):
            lines = diagram.split("\n")
            diagram = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        # Ensure valid Mermaid syntax
        if not diagram.startswith(("graph", "flowchart", "sequenceDiagram")):
            diagram = f"flowchart TD\n{diagram}"

        return diagram

    except Exception as e:
        logger.warning(f"Mermaid generation failed: {e}")
        # Return simple default diagram
        return f"""flowchart TD
    Client[Client] --> API[API Layer]
    API --> Service[Business Logic]
    Service --> DB[(Database)]
"""


async def _generate_adrs(ctx: ProjectContext, llm: LLMClient) -> List[ADR]:
    """Generate Architecture Decision Records."""

    # Build decisions summary
    decisions_summary = []

    if ctx.proposed_architecture:
        decisions_summary.append({
            "type": "Pattern",
            "decision": ctx.proposed_architecture.pattern,
            "justification": ctx.proposed_architecture.justification[:200]
        })

    for comp in ctx.tech_stack[:3]:
        decisions_summary.append({
            "type": comp.layer,
            "decision": comp.technology,
            "justification": comp.reason
        })

    prompt = ADR_PROMPT.format(decisions=decisions_summary)

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=ADRsResponse,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response.adrs
    except Exception as e:
        logger.warning(f"ADR generation failed: {e}")
        # Return minimal ADRs
        return [
            ADR(
                id="ADR-001",
                title="בחירת Architectural Pattern",
                context="נדרש לבחור Pattern ארכיטקטוני מתאים לדרישות",
                decision=f"נבחר {ctx.proposed_architecture.pattern if ctx.proposed_architecture else 'N/A'}",
                consequences=["יש לעקוב אחרי Best Practices של ה-Pattern"]
            )
        ]


async def _generate_roadmap(ctx: ProjectContext, llm: LLMClient) -> RoadmapResponse:
    """Generate implementation roadmap."""

    project_details = f"""
שם: {ctx.project_name}
Pattern: {ctx.proposed_architecture.pattern if ctx.proposed_architecture else 'N/A'}
Tech Stack: {[c.technology for c in ctx.tech_stack[:5]]}
עדיפויות: {ctx.decision_profile or ctx.priority_ranking}
"""

    time_estimate = ctx.feasibility.time_estimate if ctx.feasibility else "לא הוערך"

    prompt = ROADMAP_PROMPT.format(
        project_details=project_details,
        time_estimate=time_estimate
    )

    try:
        response = await llm.generate_structured(
            prompt=prompt,
            response_model=RoadmapResponse,
            system_prompt=BASE_SYSTEM_PROMPT
        )
        return response
    except Exception as e:
        logger.warning(f"Roadmap generation failed: {e}")
        return RoadmapResponse(
            phases={
                "Phase 1 - Foundation": ["Setup project", "Configure CI/CD", "Database setup"],
                "Phase 2 - Core": ["Implement core features", "Integration tests"],
                "Phase 3 - Production": ["Performance testing", "Security review", "Deploy"]
            },
            next_steps=["לתכנן את Phase 1 בפירוט", "להגדיר מדדי הצלחה"],
            assumptions=["צוות זמין", "תקציב מאושר"]
        )


def _format_blueprint_as_markdown(ctx: ProjectContext) -> str:
    """Format the blueprint as a Markdown document."""

    bp = ctx.blueprint
    if not bp:
        return "❌ Blueprint לא נוצר"

    parts = [
        f"# 📋 Architecture Blueprint: {ctx.project_name or 'Project'}\n",
        "---\n",
        "## 📝 Executive Summary\n",
        bp.executive_summary,
        "\n---\n",
        "## 🏗️ Architecture Diagram\n",
        "```mermaid",
        bp.mermaid_diagram,
        "```\n",
    ]

    # ADRs
    if bp.adrs:
        parts.append("## 📚 Architecture Decision Records (ADRs)\n")
        for adr in bp.adrs:
            parts.append(f"### {adr.id}: {adr.title}\n")
            parts.append(f"**Context:** {adr.context}\n")
            parts.append(f"**Decision:** {adr.decision}\n")
            parts.append("**Consequences:**")
            for cons in adr.consequences:
                parts.append(f"  - {cons}")
            parts.append("")

    # Roadmap
    if bp.roadmap:
        parts.append("## 🗺️ Implementation Roadmap\n")
        for phase, tasks in bp.roadmap.items():
            parts.append(f"### {phase}")
            for task in tasks:
                parts.append(f"  - [ ] {task}")
            parts.append("")

    # Next Steps
    if bp.next_steps:
        parts.append("## ➡️ Next Steps\n")
        for i, step in enumerate(bp.next_steps, 1):
            parts.append(f"{i}. {step}")
        parts.append("")

    # Assumptions & Unknowns
    if bp.assumptions:
        parts.append("## 📌 Assumptions\n")
        for assumption in bp.assumptions:
            parts.append(f"  - {assumption}")
        parts.append("")

    if bp.unknowns:
        parts.append("## ❓ Open Questions\n")
        for unknown in bp.unknowns:
            parts.append(f"  - {unknown}")
        parts.append("")

    parts.append("---\n")
    parts.append(f"*נוצר ע\"י Architect Agent | Confidence: {ctx.confidence_score:.0%}*")

    return "\n".join(parts)
