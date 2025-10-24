import logging

# Log configuration (before other imports)
# ruff: noqa: E402
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from app.api.base import api_router  # noqa: E402

app = FastAPI(
    title="Cogni Backend API",
    description="Backend API for Cogni - AI-powered task and note management",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Specify your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API routes
app.include_router(api_router)


@app.get("/")
def read_root():
    return {
        "message": "Cogni Backend API",
        "docs": "/docs",
        "version": "1.0.0"
    }
