"""
Architect Agent - API Routes
=============================
REST API endpoints for interacting with the agent.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from ..db.repositories import SessionRepository, BlueprintRepository
from ..agent.graph import run_agent, continue_conversation
from ..agent.state import ProjectContext
from .activity_reporter import create_reporter

# יצירת reporter לדיווח פעילות
reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d618rg7gi27c73bris40",
    service_name="Architect-agent"
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Architect Agent"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    message: str = Field(..., min_length=10, description="Initial project description")


class ChatRequest(BaseModel):
    """Request to continue a conversation."""
    message: str = Field(..., min_length=1, description="User message")


class SessionResponse(BaseModel):
    """Response with session details."""
    session_id: str
    project_name: Optional[str]
    current_node: str
    confidence_score: float
    is_done: bool
    response: str


class SessionSummary(BaseModel):
    """Summary of a session."""
    session_id: str
    project_name: Optional[str]
    current_node: str
    confidence_score: float
    created_at: str
    updated_at: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest, background_tasks: BackgroundTasks):
    """
    Create a new architecture session and run initial analysis.

    The agent will analyze the project description and respond with
    clarifying questions or initial recommendations.
    """
    logger.info(f"Creating new session with message: {request.message[:50]}...")
    background_tasks.add_task(reporter.report_activity, "web_user")  # דיווח פעילות ברקע

    try:
        # Create session in DB
        ctx = await SessionRepository.create(request.message)

        # Run the agent
        result = await run_agent(
            initial_message=request.message,
            session_id=ctx.session_id
        )

        # Update session in DB
        await SessionRepository.update(result)

        # Get last assistant message
        last_response = ""
        for msg in reversed(result.conversation_history):
            if msg.get("role") == "assistant":
                last_response = msg.get("content", "")
                break

        return SessionResponse(
            session_id=result.session_id,
            project_name=result.project_name,
            current_node=result.current_node,
            confidence_score=result.confidence_score,
            is_done=result.is_done(),
            response=last_response
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details including conversation history."""
    ctx = await SessionRepository.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": ctx.session_id,
        "project_name": ctx.project_name,
        "current_node": ctx.current_node,
        "confidence_score": ctx.confidence_score,
        "is_done": ctx.is_done(),
        "iteration_count": ctx.iteration_count,
        "requirements_count": len(ctx.requirements),
        "constraints_count": len(ctx.constraints),
        "conflicts_count": len(ctx.conflicts),
        "has_blueprint": ctx.blueprint is not None,
        "conversation_history": ctx.conversation_history,
        "created_at": ctx.created_at.isoformat(),
        "updated_at": ctx.updated_at.isoformat()
    }


@router.post("/sessions/{session_id}/chat", response_model=SessionResponse)
async def chat(session_id: str, request: ChatRequest):
    """
    Continue an existing conversation.

    Send a message to the agent and get a response.
    The agent may ask follow-up questions, resolve conflicts,
    or provide architecture recommendations.
    """
    logger.info(f"Chat in session {session_id}: {request.message[:50]}...")

    # Get existing session
    ctx = await SessionRepository.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        # Continue the conversation
        result = await continue_conversation(
            session_id=session_id,
            user_message=request.message,
            current_ctx=ctx
        )

        # Update session
        await SessionRepository.update(result)

        # Get last assistant message
        last_response = ""
        for msg in reversed(result.conversation_history):
            if msg.get("role") == "assistant":
                last_response = msg.get("content", "")
                break

        return SessionResponse(
            session_id=result.session_id,
            project_name=result.project_name,
            current_node=result.current_node,
            confidence_score=result.confidence_score,
            is_done=result.is_done(),
            response=last_response
        )

    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/blueprint")
async def get_blueprint(session_id: str):
    """Get the generated blueprint for a session."""
    ctx = await SessionRepository.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Session not found")

    if not ctx.blueprint:
        raise HTTPException(
            status_code=404,
            detail="Blueprint not yet generated. Continue the conversation to generate one."
        )

    return {
        "session_id": session_id,
        "project_name": ctx.project_name,
        "confidence_score": ctx.confidence_score,
        "blueprint": ctx.blueprint.model_dump()
    }


@router.get("/sessions/{session_id}/state")
async def get_state(session_id: str):
    """Get the full state for debugging/inspection."""
    ctx = await SessionRepository.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Session not found")

    return ctx.model_dump()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its blueprints."""
    deleted_session = await SessionRepository.delete(session_id)
    deleted_blueprints = await BlueprintRepository.delete(session_id)

    if not deleted_session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "message": "Session deleted",
        "session_id": session_id,
        "blueprints_deleted": deleted_blueprints
    }


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent sessions."""
    sessions = await SessionRepository.list_recent(limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/blueprints")
async def list_blueprints(limit: int = 10):
    """List recent blueprints."""
    blueprints = await BlueprintRepository.list_recent(limit)
    return {"blueprints": blueprints, "count": len(blueprints)}


# ============================================================
# UTILITY ENDPOINTS
# ============================================================

@router.get("/patterns")
async def list_patterns():
    """List available architectural patterns with their scoring attributes."""
    from ..knowledge.patterns import PATTERNS

    patterns_info = []
    for name, data in PATTERNS.items():
        patterns_info.append({
            "name": name,
            "display_name": data.get("name", name),
            "description": data.get("description", ""),
            "best_for": data.get("best_for", []),
            "scoring": data.get("scoring", {})
        })

    return {"patterns": patterns_info}


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str, keep_requirements: bool = True):
    """
    Reset a session to start fresh.

    Optionally keep the collected requirements.
    """
    ctx = await SessionRepository.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Session not found")

    # Reset state
    ctx.current_node = "intake"
    ctx.confidence_score = 0.0
    ctx.iteration_count = 0
    ctx.blueprint = None
    ctx.proposed_architecture = None
    ctx.shortlist = []
    ctx.tech_stack = []
    ctx.feasibility = None
    ctx.waiting_for_user = False
    ctx.error_message = None

    if not keep_requirements:
        ctx.requirements = []
        ctx.constraints = []
        ctx.conflicts = []
        ctx.priority_ranking = None
        ctx.decision_profile = None

    # Keep only the initial message
    if ctx.conversation_history:
        initial_msg = ctx.conversation_history[0]
        ctx.conversation_history = [initial_msg]

    await SessionRepository.update(ctx)

    return {
        "message": "Session reset",
        "session_id": session_id,
        "kept_requirements": keep_requirements
    }
