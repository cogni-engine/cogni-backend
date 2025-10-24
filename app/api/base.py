from fastapi import APIRouter
from app.api import cogno, notes, tasks, webhooks

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(cogno.router)
api_router.include_router(notes.router)
api_router.include_router(tasks.router)
api_router.include_router(webhooks.router)

