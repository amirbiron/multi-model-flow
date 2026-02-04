"""
Architect Agent - Graph Definition
===================================
LangGraph workflow definition connecting all nodes with
conditional routing based on state.

This is where the iterative loop logic is implemented.
"""
import logging
from typing import Any, Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import ProjectContext
from .nodes import (
    intake_node,
    priority_node,
    conflict_node,
    deep_dive_node,
    pattern_node,
    feasibility_node,
    blueprint_node,
    critic_node,
)
from ..llm.client import LLMClient, create_llm_client

logger = logging.getLogger(__name__)


def create_architect_graph(llm_client: LLMClient = None):
    """
    Create the LangGraph workflow for the Architect Agent.

    The flow:
    intake → priority → conflict → deep_dive → pattern → assess_feasibility → generate_blueprint → critic
                                       ↑                                              ↓
                                       └──────────── (if confidence < 0.7) ──────────┘

    Args:
        llm_client: Optional LLM client instance. If not provided, creates one.

    Returns:
        Compiled LangGraph ready for execution
    """
    if llm_client is None:
        llm_client = create_llm_client()

    # Create the state graph
    graph = StateGraph(ProjectContext)

    # ========================================
    # ADD NODES
    # ========================================

    # Wrap nodes to pass LLM client
    async def _intake(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await intake_node(state, llm_client)
        return ctx.model_dump()

    async def _priority(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await priority_node(state, llm_client)
        return ctx.model_dump()

    async def _conflict(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await conflict_node(state, llm_client)
        return ctx.model_dump()

    async def _deep_dive(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await deep_dive_node(state, llm_client)
        return ctx.model_dump()

    async def _pattern(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await pattern_node(state, llm_client)
        return ctx.model_dump()

    async def _feasibility(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await feasibility_node(state, llm_client)
        return ctx.model_dump()

    async def _blueprint(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply = await blueprint_node(state, llm_client)
        return ctx.model_dump()

    async def _critic(state: ProjectContext) -> Dict[str, Any]:
        ctx, reply, next_node = await critic_node(state, llm_client)
        # שומר את הינט הניתוב ב-dict (לא ב-model כי underscore fields לא עוברים serialization)
        ctx_dict = ctx.model_dump()
        ctx_dict["_routing_hint"] = next_node
        return ctx_dict

    # Add all nodes
    graph.add_node("intake", _intake)
    graph.add_node("priority", _priority)
    graph.add_node("conflict", _conflict)
    graph.add_node("deep_dive", _deep_dive)
    graph.add_node("pattern", _pattern)
    # שינוי שמות nodes כדי להימנע מהתנגשות עם שדות ב-state
    graph.add_node("assess_feasibility", _feasibility)
    graph.add_node("generate_blueprint", _blueprint)
    graph.add_node("critic", _critic)

    # ========================================
    # SET ENTRY POINT
    # ========================================

    graph.set_entry_point("intake")

    # ========================================
    # ADD EDGES (linear flow)
    # ========================================

    graph.add_edge("intake", "priority")
    graph.add_edge("priority", "conflict")
    graph.add_edge("conflict", "deep_dive")
    graph.add_edge("deep_dive", "pattern")
    graph.add_edge("pattern", "assess_feasibility")
    graph.add_edge("assess_feasibility", "generate_blueprint")
    graph.add_edge("generate_blueprint", "critic")

    # ========================================
    # CONDITIONAL EDGE FROM CRITIC
    # ========================================

    def _route_from_critic(state) -> str:
        """
        Routing function for conditional edge from critic.
        הלוגיקה העיקרית נמצאת ב-critic_node, כאן רק קוראים את ה-routing hint.
        """
        # ממיר ל-dict כדי לגשת ל-_routing_hint שנוסף ב-critic node
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = state.model_dump()

        routing_hint = state_dict.get("_routing_hint")

        # אם יש routing hint תקין - משתמשים בו
        if routing_hint and routing_hint in ["deep_dive", "conflict", "pattern"]:
            logger.info(f"Critic routing to: {routing_hint}")
            return routing_hint

        # אחרת - מסיימים (critic_node כבר החליט לסיים)
        logger.info("Critic routing to: end")
        return "end"

    graph.add_conditional_edges(
        "critic",
        _route_from_critic,
        {
            "deep_dive": "deep_dive",
            "conflict": "conflict",
            "pattern": "pattern",
            "end": END
        }
    )

    # ========================================
    # COMPILE WITH CHECKPOINTER
    # ========================================

    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Architect graph compiled successfully")

    return compiled


async def run_agent(
    initial_message: str,
    session_id: str,
    llm_client: LLMClient = None
) -> ProjectContext:
    """
    Run the architect agent on an initial message.

    Args:
        initial_message: The user's project description
        session_id: Unique session identifier
        llm_client: Optional LLM client

    Returns:
        Final ProjectContext with blueprint
    """
    logger.info(f"Starting agent run for session: {session_id}")

    # Create the graph
    graph = create_architect_graph(llm_client)

    # Create initial state
    initial_state = ProjectContext(
        session_id=session_id,
        initial_summary=initial_message
    )
    initial_state.add_message("user", initial_message)

    # Run configuration - מגדיל את ה-recursion limit כדי לאפשר יותר איטרציות
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 50  # ברירת מחדל היא 25, מגדילים ל-50
    }

    # Execute the graph
    result = await graph.ainvoke(initial_state.model_dump(), config)

    # Convert result back to ProjectContext
    final_ctx = ProjectContext.model_validate(result)

    logger.info(
        f"Agent run complete for session: {session_id}, "
        f"iterations: {final_ctx.iteration_count}, "
        f"confidence: {final_ctx.confidence_score:.2f}"
    )

    return final_ctx


async def continue_conversation(
    session_id: str,
    user_message: str,
    current_ctx: ProjectContext,
    llm_client: LLMClient = None
) -> ProjectContext:
    """
    Continue an existing conversation with a new user message.

    Args:
        session_id: Session identifier
        user_message: New message from user
        current_ctx: Current project context
        llm_client: Optional LLM client

    Returns:
        Updated ProjectContext
    """
    logger.info(f"Continuing conversation for session: {session_id}")

    # Add user message
    current_ctx.add_message("user", user_message)

    # Determine which node to run based on current state
    if current_ctx.waiting_for_user:
        # Process based on current node
        from .nodes import (
            process_priority_response,
            process_conflict_response,
            process_deep_dive_response
        )

        if current_ctx.current_node == "priority":
            process_priority_response(current_ctx, user_message)
        elif current_ctx.current_node == "conflict":
            process_conflict_response(current_ctx, user_message)
        elif current_ctx.current_node == "deep_dive":
            process_deep_dive_response(current_ctx, user_message)
        elif current_ctx.current_node == "critic":
            # המשתמש סיפק מידע נוסף שהמבקר ביקש
            # ההודעה כבר נשמרה ב-conversation_history
            # הגרף ירוץ מההתחלה, אבל עם ה-context המעודכן שכולל את ההודעה החדשה
            pass

        current_ctx.waiting_for_user = False

    # Create and run graph from current state
    graph = create_architect_graph(llm_client)
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 50
    }

    result = await graph.ainvoke(current_ctx.model_dump(), config)
    final_ctx = ProjectContext.model_validate(result)

    return final_ctx
