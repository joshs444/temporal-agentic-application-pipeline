"""
Pydantic models for JobHunt API request/response schemas.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Enums for status fields
class JobStatus(str, Enum):
    NEW = "new"
    INTERESTED = "interested"
    APPLYING = "applying"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    DISMISSED = "dismissed"


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InterviewStage(str, Enum):
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    FINAL = "final"


class InterviewOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


class RemoteType(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


# Base models
class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime


# Job models
class JobBase(BaseModel):
    title: str
    company_name: str
    location: Optional[str] = None
    remote_type: Optional[RemoteType] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    description: Optional[str] = None
    requirements: Optional[str] = None
    url: Optional[str] = None


class JobResponse(BaseModel):
    id: UUID
    external_id: Optional[str] = None
    source: str
    title: str
    company_name: str
    company_url: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    url: Optional[str] = None
    posted_at: Optional[datetime] = None
    match_score: Optional[Decimal] = Field(None, alias="fit_score")
    fit_score: Optional[float] = None
    status: str = "new"
    category: Optional[str] = None
    skills_matched: Optional[list[str]] = None
    skills_missing: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class JobDetailResponse(JobResponse):
    description: Optional[str] = None
    requirements: Optional[str] = None
    score_breakdown: Optional[dict[str, Any]] = None
    raw_data: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    company: Optional["CompanyResponse"] = None
    application: Optional["ApplicationResponse"] = None


class JobUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[int] = None
    notes: Optional[str] = None
    match_score: Optional[Decimal] = None


class JobCreate(JobBase):
    source: str = "manual"
    external_id: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


# Application models
class ApplicationBase(BaseModel):
    resume_version: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    applied_at: Optional[datetime] = None
    resume_version: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApplicationDetailResponse(ApplicationResponse):
    custom_answers: Optional[dict[str, Any]] = None
    job: Optional[JobResponse] = None
    interviews: list["InterviewResponse"] = []


class ApplicationCreate(BaseModel):
    job_id: UUID
    method: str = "email"  # 'email', 'portal', 'referral'
    resume_version: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    cover_letter: Optional[str] = None
    custom_answers: Optional[dict[str, Any]] = None


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationResponse]
    total: int


# Interview models
class InterviewResponse(BaseModel):
    id: UUID
    application_id: UUID
    stage: str
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    interviewer_names: Optional[list[str]] = None
    interviewer_titles: Optional[list[str]] = None
    prep_notes: Optional[str] = None
    questions_to_ask: Optional[str] = None
    feedback: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InterviewCreate(BaseModel):
    stage: str
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = 60
    location: Optional[str] = None
    interviewer_names: Optional[list[str]] = None
    interviewer_titles: Optional[list[str]] = None
    notes: Optional[str] = None


class InterviewUpdate(BaseModel):
    stage: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    interviewer_names: Optional[list[str]] = None
    interviewer_titles: Optional[list[str]] = None
    prep_notes: Optional[str] = None
    questions_to_ask: Optional[str] = None
    feedback: Optional[str] = None
    outcome: Optional[str] = None


# Company models
class CompanyResponse(BaseModel):
    id: UUID
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    size_range: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    linkedin_url: Optional[str] = None
    glassdoor_url: Optional[str] = None
    glassdoor_rating: Optional[Decimal] = None
    funding_stage: Optional[str] = None
    total_funding: Optional[int] = None
    enriched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompanyCreate(BaseModel):
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    size_range: Optional[str] = None
    description: Optional[str] = None


class CompanyUpdate(BaseModel):
    domain: Optional[str] = None
    industry: Optional[str] = None
    size_range: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    linkedin_url: Optional[str] = None


class CompanyListResponse(BaseModel):
    companies: list[CompanyResponse]
    total: int


# Search config models
class SearchConfigResponse(BaseModel):
    id: UUID
    name: str
    query_params: dict[str, Any]
    is_active: bool
    last_run_at: Optional[datetime] = None
    run_frequency_hours: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SearchConfigCreate(BaseModel):
    name: str
    query_params: dict[str, Any]
    is_active: bool = True
    run_frequency_hours: int = 24


class SearchConfigUpdate(BaseModel):
    name: Optional[str] = None
    query_params: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    run_frequency_hours: Optional[int] = None


# Dashboard models
class DashboardStats(BaseModel):
    jobs_total: int
    jobs_this_week: int
    applications_total: int
    applications_this_week: int
    interviews_scheduled: int
    response_rate: float
    avg_fit_score: Optional[float] = None


class PipelineStage(BaseModel):
    status: str
    count: int
    jobs: list[JobResponse]


class PipelineResponse(BaseModel):
    stages: list[PipelineStage]
    total: int


class ActivityEvent(BaseModel):
    id: UUID
    event_type: str  # 'job_discovered', 'application_sent', 'interview_scheduled', etc.
    title: str
    description: Optional[str] = None
    entity_type: str  # 'job', 'application', 'interview'
    entity_id: UUID
    occurred_at: datetime


class ActivityFeed(BaseModel):
    events: list[ActivityEvent]
    days: int


# Workflow models
class WorkflowTriggerResponse(BaseModel):
    status: str
    workflow_id: str
    message: Optional[str] = None


class ApplicationDraft(BaseModel):
    job_id: UUID
    cover_letter: Optional[str] = None
    resume_version: Optional[str] = None
    custom_answers: Optional[dict[str, Any]] = None
    method: str
    status: str  # 'pending_approval', 'approved', 'rejected'
    created_at: datetime


class ApplicationApproval(BaseModel):
    approved: bool
    edits: Optional[dict[str, Any]] = None


# Update forward references
JobDetailResponse.model_rebuild()
ApplicationDetailResponse.model_rebuild()
