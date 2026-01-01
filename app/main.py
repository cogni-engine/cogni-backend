import logging

# Log configuration (before other imports)
# ruff: noqa: E402
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

from fastapi import FastAPI, APIRouter  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from app.api import cogno, notes, tasks, webhooks, push_notifications, users  # noqa: E402

app = FastAPI(
    title="Cogni Backend API",
    description="Backend API for Cogni - AI-powered task and note management",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Include all API routes
app.include_router(api_router)


@app.get("/")
def read_root():
    return {
        "message": "Cogni Backend API",
        "docs": "/docs",
        "version": "1.0.0"
    }
