"""
Architect Agent - MongoDB Client
=================================
Async MongoDB client with connection pooling and index management.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING
from typing import Optional
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """
    MongoDB client wrapper with connection pooling.
    Uses singleton pattern for efficient connection management.
    """

    client: Optional[AsyncIOMotorClient] = None
    db = None

    @classmethod
    async def connect(cls):
        """Create connection to MongoDB."""
        if cls.client is None:
            logger.info(f"Connecting to MongoDB: {settings.MONGODB_DB_NAME}")
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                serverSelectionTimeoutMS=5000
            )
            cls.db = cls.client[settings.MONGODB_DB_NAME]

            # Create indexes
            await cls._create_indexes()

            logger.info("Connected to MongoDB successfully")

    @classmethod
    async def disconnect(cls):
        """Close the connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Disconnected from MongoDB")

    @classmethod
    async def _create_indexes(cls):
        """Create required indexes for optimal performance."""
        try:
            # Sessions collection
            sessions = cls.db.sessions
            await sessions.create_indexes([
                IndexModel([("session_id", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel(
                    [("updated_at", ASCENDING)],
                    expireAfterSeconds=86400 * 30  # TTL: 30 days
                )
            ])

            # Blueprints collection
            blueprints = cls.db.blueprints
            await blueprints.create_indexes([
                IndexModel([("session_id", ASCENDING)]),
                IndexModel([("project_name", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)])
            ])

            # Patterns knowledge collection
            patterns = cls.db.patterns
            await patterns.create_indexes([
                IndexModel([("name", ASCENDING)], unique=True)
            ])

            logger.info("MongoDB indexes created")

        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    @classmethod
    def get_collection(cls, name: str):
        """Get a collection by name."""
        if cls.db is None:
            raise RuntimeError("Database not connected. Call MongoDB.connect() first.")
        return cls.db[name]

    @classmethod
    async def ping(cls) -> bool:
        """Check if MongoDB is reachable."""
        try:
            if cls.client:
                await cls.client.admin.command('ping')
                return True
        except Exception:
            pass
        return False


# Dependency injection for FastAPI
async def get_db():
    """Dependency for injecting DB into routes."""
    if MongoDB.client is None:
        await MongoDB.connect()
    return MongoDB
