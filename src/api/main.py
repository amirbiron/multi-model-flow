"""
Architect Agent - FastAPI Application
======================================
Main application entry point with lifespan management.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from .routes import router
from ..db.mongodb import MongoDB
from ..config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for startup and shutdown."""
    # Startup
    logger.info("Starting Architect Agent API...")
    await MongoDB.connect()
    yield
    # Shutdown
    logger.info("Shutting down Architect Agent API...")
    await MongoDB.disconnect()


app = FastAPI(
    title="Architect Agent API",
    description="AI-powered software architecture advisor using LangGraph",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routes
app.include_router(router, prefix="/api")

# נתיב לתיקיית הקבצים הסטטיים
STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/")
async def root():
    """מחזיר את דף הבית (ממשק הווב)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_ok = await MongoDB.ping()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected"
    }
