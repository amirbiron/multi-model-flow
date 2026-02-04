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
    ask_user_node,
    process_user_answers,
)
from ..llm.client import LLMClient, create_llm_client

logger = logging.getLogger(__name__)


def create_architect_graph(llm_client: LLMClient = None):
    """
    Create the LangGraph workflow for the Architect Agent.

    The flow (with dynamic entry point):
    router → [intake|priority|deep_dive|assess_feasibility] → ... → critic
                                       ↑                              ↓
                                       └──── (if needs revision) ─────┘

    Router logic:
    - אם יש blueprint → ממשיך מ-deep_dive
    - אם יש proposed_architecture → ממשיך מ-assess_feasibility
    - אם יש requirements → ממשיך מ-priority
    - אחרת → מתחיל מ-intake

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

    # פונקציית עזר להמרת state ל-ProjectContext
    def _to_ctx(state) -> ProjectContext:
        """ממיר dict ל-ProjectContext אם צריך."""
        if isinstance(state, ProjectContext):
            return state
        return ProjectContext.model_validate(state)

    # Wrap nodes to pass LLM client
    async def _intake(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await intake_node(ctx, llm_client)
        return ctx.model_dump()

    async def _priority(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await priority_node(ctx, llm_client)
        return ctx.model_dump()

    async def _conflict(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await conflict_node(ctx, llm_client)
        return ctx.model_dump()

    async def _deep_dive(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await deep_dive_node(ctx, llm_client)
        return ctx.model_dump()

    async def _pattern(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await pattern_node(ctx, llm_client)
        return ctx.model_dump()

    async def _feasibility(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await feasibility_node(ctx, llm_client)
        return ctx.model_dump()

    async def _blueprint(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply = await blueprint_node(ctx, llm_client)
        return ctx.model_dump()

    async def _critic(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        ctx, reply, next_node, questions = await critic_node(ctx, llm_client)
        # שומר את הינט הניתוב ב-dict (לא ב-model כי underscore fields לא עוברים serialization)
        ctx_dict = ctx.model_dump()
        ctx_dict["_routing_hint"] = next_node
        # שומר את השאלות אם יש - ישמשו את ask_user_node
        if questions:
            ctx_dict["_pending_questions"] = [q.model_dump() for q in questions]
        return ctx_dict

    async def _ask_user(state) -> Dict[str, Any]:
        ctx = _to_ctx(state)
        # לקיחת השאלות מה-state אם יש
        questions = None
        if isinstance(state, dict) and "_pending_questions" in state:
            from .state import CriticQuestion
            questions = [CriticQuestion(**q) for q in state["_pending_questions"]]
        ctx, reply, should_continue = await ask_user_node(ctx, llm_client, questions)
        ctx_dict = ctx.model_dump()
        # אם צריך להמשיך (אין שאלות חדשות), מעביר hint לגרף
        ctx_dict["_ask_user_should_continue"] = should_continue
        return ctx_dict

    # Add all nodes to the graph
    graph.add_node("intake", _intake)
    graph.add_node("priority", _priority)
    graph.add_node("conflict", _conflict)
    graph.add_node("deep_dive", _deep_dive)
    graph.add_node("pattern", _pattern)
    graph.add_node("assess_feasibility", _feasibility)
    graph.add_node("generate_blueprint", _blueprint)
    graph.add_node("critic", _critic)
    graph.add_node("ask_user", _ask_user)  # Node חדש לשאילת שאלות

    # ========================================
    # ROUTER NODE - מחליט מאיפה להתחיל
    # ========================================

    def _route_entry(state) -> str:
        """
        Router שמחליט מאיפה להתחיל/להמשיך.
        אם יש כבר blueprint - ממשיכים מ-deep_dive (לאסוף מידע נוסף)
        אם יש כבר pattern - ממשיכים מ-assess_feasibility
        אחרת - מתחילים מ-intake
        """
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = state.model_dump()

        # אם יש blueprint - אנחנו בשלב מתקדם, צריך רק להוסיף מידע
        if state_dict.get("blueprint"):
            logger.info("Router: blueprint exists, starting from deep_dive")
            return "deep_dive"

        # אם יש proposed_architecture - ממשיכים משם
        if state_dict.get("proposed_architecture"):
            logger.info("Router: architecture exists, starting from assess_feasibility")
            return "assess_feasibility"

        # אם יש requirements - ממשיכים מ-priority
        if state_dict.get("requirements"):
            logger.info("Router: requirements exist, starting from priority")
            return "priority"

        # אחרת - מתחילים מההתחלה
        logger.info("Router: starting from intake")
        return "intake"

    # Add router as entry point - מוודא שמחזיר dict
    def _router_node(state):
        """Router node - מחזיר את ה-state כ-dict."""
        if isinstance(state, dict):
            return state
        return state.model_dump()

    graph.add_node("router", _router_node)

    # ========================================
    # SET ENTRY POINT
    # ========================================

    graph.set_entry_point("router")

    # ========================================
    # ADD EDGES
    # ========================================

    # Router edges - מנתב לנקודת התחלה מתאימה
    graph.add_conditional_edges(
        "router",
        _route_entry,
        {
            "intake": "intake",
            "priority": "priority",
            "deep_dive": "deep_dive",
            "assess_feasibility": "assess_feasibility",
        }
    )

    # Linear flow edges
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

        ## Verdicts ו-Routing:
        - accept / accept_with_notes -> END
        - ask_user -> ask_user node (שואל את המשתמש)
        - swap_option -> pattern node (עם forced_pattern)
        """
        # ממיר ל-dict כדי לגשת ל-_routing_hint שנוסף ב-critic node
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = state.model_dump()

        routing_hint = state_dict.get("_routing_hint")

        # אם יש routing hint תקין - משתמשים בו
        if routing_hint and routing_hint in ["ask_user", "deep_dive", "conflict", "pattern"]:
            logger.info(f"Critic routing to: {routing_hint}")
            return routing_hint

        # אחרת - מסיימים (critic_node כבר החליט לסיים)
        logger.info("Critic routing to: end")
        return "end"

    graph.add_conditional_edges(
        "critic",
        _route_from_critic,
        {
            "ask_user": "ask_user",  # verdict=ask_user: שואל את המשתמש
            "deep_dive": "deep_dive",
            "conflict": "conflict",
            "pattern": "pattern",     # verdict=swap_option: מחליף pattern
            "end": END
        }
    )

    # ask_user - conditional routing based on should_continue
    def _route_from_ask_user(state) -> str:
        """
        Routing function for ask_user node.
        אם יש שאלות חדשות - מחכים למשתמש (END).
        אם אין שאלות חדשות - ממשיכים לתהליך (generate_blueprint).
        """
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = state.model_dump()

        should_continue = state_dict.get("_ask_user_should_continue", False)

        if should_continue:
            logger.info("ask_user: no new questions, continuing to generate_blueprint")
            return "continue"
        else:
            logger.info("ask_user: waiting for user response")
            return "end"

    graph.add_conditional_edges(
        "ask_user",
        _route_from_ask_user,
        {
            "continue": "generate_blueprint",  # אין שאלות חדשות - ממשיכים
            "end": END                         # יש שאלות - מחכים למשתמש
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

    # המרת התוצאה ל-ProjectContext - בדיקה אם כבר אובייקט או dict
    if isinstance(result, ProjectContext):
        final_ctx = result
    else:
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

    # יצירת llm_client אם לא סופק
    if llm_client is None:
        llm_client = create_llm_client()

    # Determine which node to run based on current state
    if current_ctx.waiting_for_user:
        # Process based on current node
        from .nodes import (
            process_priority_response,
            process_conflict_response,
            process_deep_dive_response,
            process_user_answers
        )

        if current_ctx.current_node == "priority":
            process_priority_response(current_ctx, user_message)
        elif current_ctx.current_node == "conflict":
            process_conflict_response(current_ctx, user_message)
        elif current_ctx.current_node == "deep_dive":
            process_deep_dive_response(current_ctx, user_message)
        elif current_ctx.current_node == "ask_user":
            # המשתמש ענה על שאלות מ-ask_user node
            # מעבדים את התשובות ומעדכנים את facts
            current_ctx = await process_user_answers(current_ctx, user_message, llm_client)
        elif current_ctx.current_node == "critic":
            # המשתמש סיפק מידע נוסף שהמבקר ביקש (legacy - בדרך כלל עכשיו עובר דרך ask_user)
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

    # המרת התוצאה ל-ProjectContext - בדיקה אם כבר אובייקט או dict
    if isinstance(result, ProjectContext):
        final_ctx = result
    else:
        final_ctx = ProjectContext.model_validate(result)

    return final_ctx
