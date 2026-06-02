"""
Job Worker - FastAPI application with Temporal worker integration.

This is the main entry point for the job-worker service.
Provides REST API for job search automation and tracking.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from temporalio.client import Client as TemporalClient

from routes import (
    jobs_router,
    applications_router,
    companies_router,
    workflows_router,
    dashboard_router,
    resume_router,
)
from routes.workflows import set_temporal_client
from utils.database import get_pool, close_pool
from scheduler import run_scheduler

# Configuration
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@localhost:6380/0")
API_KEY = os.getenv("JOBHUNT_API_KEY", "dev-api-key")  # Set in production!
API_KEY_NAME = "X-API-Key"

# API Key security
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Verify the API key from the request header.

    In development mode (API_KEY="dev-api-key"), authentication is relaxed.
    In production, a valid API key is required for all endpoints.
    """
    # Skip auth for health check
    if api_key is None:
        if API_KEY == "dev-api-key":
            return "dev"
        raise HTTPException(
            status_code=401,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    services: dict[str, str]


# Global Temporal client
temporal_client: Optional[TemporalClient] = None
# Global scheduler task
scheduler_task: Optional[asyncio.Task] = None


async def get_temporal_client() -> TemporalClient:
    """Get or create Temporal client."""
    global temporal_client
    if temporal_client is None:
        temporal_client = await TemporalClient.connect(TEMPORAL_ADDRESS)
        # Share with workflows router
        set_temporal_client(temporal_client)
    return temporal_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global scheduler_task

    # Startup
    print("Starting Job Worker API...")
    print(f"Temporal Address: {TEMPORAL_ADDRESS}")
    print(f"Database URL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured'}")

    # Initialize database pool
    try:
        await get_pool()
        print("Connected to database")
    except Exception as e:
        print(f"Warning: Could not connect to database: {e}")

    # Initialize Temporal client
    try:
        client = await get_temporal_client()
        print("Connected to Temporal")

        # Start scheduler
        scheduler_task = asyncio.create_task(run_scheduler(client))
        print("Started discovery scheduler")
    except Exception as e:
        print(f"Warning: Could not connect to Temporal: {e}")

    yield

    # Shutdown
    print("Shutting down Job Worker API...")

    # Cancel scheduler task
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            print("Scheduler task cancelled")

    # Close database pool
    await close_pool()

    # Close Temporal client
    if temporal_client:
        await temporal_client.close() if hasattr(temporal_client, 'close') else None


# Create FastAPI app
app = FastAPI(
    title="JobHunt API",
    description="Job search automation and tracking API",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Disable auto-redirect to avoid issues behind nginx proxy
)

# CORS middleware - allow all origins for API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Can't use credentials with wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers with API key dependency
app.include_router(
    jobs_router,
    prefix="/api/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    applications_router,
    prefix="/api/applications",
    tags=["applications"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    companies_router,
    prefix="/api/companies",
    tags=["companies"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    workflows_router,
    prefix="/api/workflows",
    tags=["workflows"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    dashboard_router,
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    resume_router,
    prefix="/api/resume",
    tags=["resume"],
    dependencies=[Depends(verify_api_key)],
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    No authentication required for health checks.
    """
    services = {
        "api": "healthy",
        "temporal": "unknown",
        "database": "unknown",
        "redis": "unknown",
    }

    # Check Temporal connection
    try:
        client = await get_temporal_client()
        if client:
            services["temporal"] = "healthy"
    except Exception:
        services["temporal"] = "unhealthy"

    # Check database connection
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            services["database"] = "healthy"
    except Exception:
        services["database"] = "unhealthy"

    return HealthResponse(
        status="healthy" if all(s == "healthy" for s in services.values() if s != "unknown") else "degraded",
        version="1.0.0",
        services=services,
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "service": "jobhunt-api",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/api")
async def api_info() -> dict[str, Any]:
    """API information and available endpoints."""
    return {
        "name": "JobHunt API",
        "version": "1.0.0",
        "endpoints": {
            "jobs": "/api/jobs",
            "applications": "/api/applications",
            "companies": "/api/companies",
            "workflows": "/api/workflows",
            "dashboard": "/api/dashboard",
            "resume": "/api/resume",
        },
        "documentation": "/docs",
        "authentication": f"Include '{API_KEY_NAME}' header with your API key",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
