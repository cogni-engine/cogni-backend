"""Health check and monitoring endpoints"""

from fastapi import APIRouter
from app.db.session import get_pool_stats

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/pool")
async def get_pool_health():
    """
    Get connection pool health statistics.
    
    Returns pool utilization, connection counts, and health status.
    """
    stats = get_pool_stats()
    available = stats["checked_in"]
    in_use = stats["checked_out"]
    total_capacity = stats["size"] + stats["max_overflow"]
    utilization = (in_use / total_capacity * 100) if total_capacity > 0 else 0
    
    # Determine health status
    if utilization >= 90:
        status = "critical"
    elif utilization >= 80:
        status = "warning"
    else:
        status = "healthy"
    
    return {
        "status": status,
        "pool_size": stats["size"],
        "max_overflow": stats["max_overflow"],
        "available": available,
        "in_use": in_use,
        "overflow": stats["overflow"],
        "invalid": stats["invalid"],
        "utilization_percent": round(utilization, 2),
        "total_capacity": total_capacity,
    }


@router.get("/")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "cogni-backend",
    }
