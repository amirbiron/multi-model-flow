"""
Architect Agent - Repositories
===============================
Data Access Layer for MongoDB operations.
"""
from typing import Optional, List
from datetime import datetime
import uuid
import logging

from .mongodb import MongoDB
from ..agent.state import ProjectContext, Blueprint

logger = logging.getLogger(__name__)


class SessionRepository:
    """Repository for Session/ProjectContext operations."""

    @staticmethod
    async def create(initial_message: str) -> ProjectContext:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        ctx = ProjectContext(
            session_id=session_id,
            initial_summary=initial_message
        )
        ctx.add_message("user", initial_message)

        collection = MongoDB.get_collection("sessions")
        await collection.insert_one(ctx.model_dump())

        logger.info(f"Created session: {session_id}")
        return ctx

    @staticmethod
    async def get(session_id: str) -> Optional[ProjectContext]:
        """Get session by ID."""
        collection = MongoDB.get_collection("sessions")
        doc = await collection.find_one({"session_id": session_id})

        if doc:
            # Remove MongoDB _id field
            doc.pop("_id", None)
            return ProjectContext.model_validate(doc)
        return None

    @staticmethod
    async def update(ctx: ProjectContext) -> bool:
        """Update an existing session."""
        ctx.updated_at = datetime.utcnow()

        collection = MongoDB.get_collection("sessions")
        result = await collection.replace_one(
            {"session_id": ctx.session_id},
            ctx.model_dump()
        )

        return result.modified_count > 0

    @staticmethod
    async def add_message(session_id: str, role: str, content: str):
        """Add a message to session history."""
        collection = MongoDB.get_collection("sessions")
        await collection.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "conversation_history": {
                        "role": role,
                        "content": content,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

    @staticmethod
    async def delete(session_id: str) -> bool:
        """Delete a session."""
        collection = MongoDB.get_collection("sessions")
        result = await collection.delete_one({"session_id": session_id})
        return result.deleted_count > 0

    @staticmethod
    async def list_recent(limit: int = 20) -> List[dict]:
        """List recent sessions."""
        collection = MongoDB.get_collection("sessions")
        cursor = collection.find(
            {},
            {
                "session_id": 1,
                "project_name": 1,
                "current_node": 1,
                "confidence_score": 1,
                "created_at": 1,
                "updated_at": 1
            }
        ).sort("updated_at", -1).limit(limit)

        results = await cursor.to_list(length=limit)
        for r in results:
            r.pop("_id", None)
        return results


class BlueprintRepository:
    """Repository for Blueprint documents."""

    @staticmethod
    async def save(session_id: str, blueprint: Blueprint, project_name: str):
        """Save a generated blueprint."""
        collection = MongoDB.get_collection("blueprints")

        doc = {
            "session_id": session_id,
            "project_name": project_name,
            "blueprint": blueprint.model_dump(),
            "created_at": datetime.utcnow()
        }

        await collection.insert_one(doc)
        logger.info(f"Saved blueprint for session: {session_id}")

    @staticmethod
    async def get_by_session(session_id: str) -> Optional[Blueprint]:
        """Get the most recent blueprint for a session."""
        collection = MongoDB.get_collection("blueprints")
        doc = await collection.find_one(
            {"session_id": session_id},
            sort=[("created_at", -1)]
        )

        if doc:
            return Blueprint.model_validate(doc["blueprint"])
        return None

    @staticmethod
    async def list_recent(limit: int = 10) -> List[dict]:
        """List recent blueprints."""
        collection = MongoDB.get_collection("blueprints")
        cursor = collection.find(
            {},
            {
                "session_id": 1,
                "project_name": 1,
                "created_at": 1,
                "blueprint.executive_summary": 1
            }
        ).sort("created_at", -1).limit(limit)

        results = await cursor.to_list(length=limit)
        for r in results:
            r.pop("_id", None)
        return results

    @staticmethod
    async def delete(session_id: str) -> int:
        """Delete all blueprints for a session."""
        collection = MongoDB.get_collection("blueprints")
        result = await collection.delete_many({"session_id": session_id})
        return result.deleted_count
