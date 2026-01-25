import logging
import os

# Log configuration (before other imports)
# ruff: noqa: E402
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

from fastapi import FastAPI, APIRouter  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from app.api import cogno, notes, tasks, webhooks, push_notifications, users, note_ai_editor, onboarding, organizations  # noqa: E402
from app.features import ai_notifications, billing  # noqa: E402

app = FastAPI(
    title="Cogni Backend API",
    description="Backend API for Cogni - AI-powered task and note management",  
    version="1.0.0"
)

# Configure CORS with specific origins
# When allow_credentials=True, we cannot use allow_origins=["*"]
# We need to specify exact origins
def get_allowed_origins() -> list[str]:
    """Get list of allowed CORS origins from environment variables"""
    origins = []
    
    # Add CLIENT_URL if set
    client_url = os.getenv("CLIENT_URL", "http://localhost:3000")
    if client_url:
        origins.append(client_url)
    
    # Add Supabase URL if set
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        origins.append(supabase_url)
    
    # Add additional origins from ALLOWED_ORIGINS env var (comma-separated)
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if allowed_origins_env:
        origins.extend([origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()])
    
    # Always include localhost for development
    if "http://localhost:3000" not in origins:
        origins.append("http://localhost:3000")
    if "http://127.0.0.1:3000" not in origins:
        origins.append("http://127.0.0.1:3000")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_origins = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            unique_origins.append(origin)
    
    logging.info(f"CORS allowed origins: {unique_origins}")
    return unique_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API router and include all sub-routers
api_router = APIRouter()
api_router.include_router(cogno.router)
api_router.include_router(notes.router)
api_router.include_router(tasks.router)
api_router.include_router(webhooks.router)
api_router.include_router(push_notifications.router)
api_router.include_router(users.router)
api_router.include_router(note_ai_editor.router)
api_router.include_router(onboarding.router)
api_router.include_router(organizations.router)
api_router.include_router(ai_notifications.router)
api_router.include_router(billing.router)

# Include all API routes
app.include_router(api_router)


@app.get("/")
def read_root():
    return {
        "message": "Cogni Backend API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections on shutdown"""
    from app.db.session import engine
    await engine.dispose()
