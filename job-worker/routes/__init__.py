"""
API Routes for JobHunt.
"""

from .jobs import router as jobs_router
from .applications import router as applications_router
from .companies import router as companies_router
from .workflows import router as workflows_router
from .dashboard import router as dashboard_router
from .resume import router as resume_router

__all__ = [
    "jobs_router",
    "applications_router",
    "companies_router",
    "workflows_router",
    "dashboard_router",
    "resume_router",
]
