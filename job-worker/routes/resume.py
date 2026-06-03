"""
Resume profile endpoints for JobHunt API.

Handles resume upload, parsing, and profile management.
"""

import hashlib
import io
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from utils.database import fetch_one, fetch_all, execute, record_to_dict
from utils.llm_config import LLM_API_KEY, LLM_BASE_URL, LLM_LIGHT_MODEL

router = APIRouter()

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


class ResumeProfileResponse(BaseModel):
    """Resume profile response model."""
    id: UUID
    name: str
    description: Optional[str] = None
    is_default: bool
    file_path: Optional[str] = None
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    experience_summary: Optional[str] = None
    target_titles: Optional[list[str]] = None
    preferred_remote: Optional[str] = None
    preferred_locations: Optional[list[str]] = None
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    times_used: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResumeProfileDetailResponse(ResumeProfileResponse):
    """Detailed resume profile with all fields."""
    raw_text: Optional[str] = None
    parsed_data: Optional[dict[str, Any]] = None
    skill_levels: Optional[dict[str, str]] = None
    certifications: Optional[list[str]] = None
    key_achievements: Optional[list[str]] = None
    education: Optional[dict[str, Any]] = None
    target_industries: Optional[list[str]] = None
    preferred_remote: Optional[str] = None


class ResumeProfileCreate(BaseModel):
    """Create resume profile request."""
    name: str
    description: Optional[str] = None
    is_default: bool = False
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    experience_summary: Optional[str] = None
    target_titles: Optional[list[str]] = None
    target_industries: Optional[list[str]] = None
    preferred_remote: Optional[str] = None
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None


class ResumeProfileUpdate(BaseModel):
    """Update resume profile request."""
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    experience_summary: Optional[str] = None
    target_titles: Optional[list[str]] = None
    target_industries: Optional[list[str]] = None
    preferred_remote: Optional[str] = None
    preferred_locations: Optional[list[str]] = None
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None


class ResumeListResponse(BaseModel):
    """List of resume profiles."""
    profiles: list[ResumeProfileResponse]
    total: int


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        # Fallback to PyPDF2 if pdfplumber not available
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_content))
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="PDF parsing libraries not installed"
            )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse PDF: {str(e)}"
        )


async def extract_skills_from_text_llm(text: str) -> list[str]:
    """Extract skills from resume text using LLM."""
    import httpx

    if not LLM_API_KEY:
        # Fallback to basic extraction if no API key
        return extract_skills_basic(text)

    prompt = f"""Extract technical skills from this resume. Return ONLY a JSON array of skill strings.

Rules:
- Include programming languages, frameworks, databases, cloud platforms, tools
- Use proper capitalization (e.g., "Python", "AWS", "PostgreSQL", "React")
- Only include skills that are EXPLICITLY mentioned
- Do NOT infer skills or include skills that aren't clearly stated
- Maximum 20 most relevant skills

Resume:
{text[:4000]}

Return ONLY a JSON array like: ["Python", "React", "PostgreSQL"]"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_LIGHT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Parse JSON array from response
            import json
            # Handle markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            skills = json.loads(content.strip())
            return skills if isinstance(skills, list) else []
    except Exception as e:
        print(f"LLM skill extraction failed: {e}, falling back to basic")
        return extract_skills_basic(text)


def extract_skills_basic(text: str) -> list[str]:
    """Basic fallback skill extraction using word boundaries."""
    import re

    skill_patterns = [
        r'\bPython\b', r'\bJavaScript\b', r'\bTypeScript\b', r'\bReact\b',
        r'\bPostgreSQL\b', r'\bDocker\b', r'\bAWS\b', r'\bRedis\b',
        r'\bFastAPI\b', r'\bNode\.js\b', r'\bTailwind\b', r'\bGit\b',
    ]

    found = []
    for pattern in skill_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            # Extract the skill name from pattern
            skill = pattern.replace(r'\b', '').replace('\\', '')
            found.append(skill)

    return list(set(found))


async def extract_job_titles_from_resume(text: str) -> list[str]:
    """Extract job titles from resume Experience section using LLM."""
    import httpx

    if not LLM_API_KEY:
        return []

    prompt = f"""Extract job titles from this resume's Experience/Work History section.

Rules:
- Only extract actual job titles the person has held (e.g., "Senior Software Engineer", "Forward Deployed Engineer")
- Include the seniority level in the title (Junior, Senior, Staff, Principal, Lead, etc.)
- Do NOT include company names - just the job titles
- Return 3-7 unique titles, most recent/senior first
- Also suggest 2-3 related titles they could search for based on their experience

Resume:
{text[:5000]}

Return ONLY a JSON object like:
{{
    "held_titles": ["Staff Engineer", "Senior Software Engineer"],
    "suggested_titles": ["Forward Deployed Engineer", "Solutions Architect", "Platform Engineer"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_LIGHT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            import json
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content.strip())

            # Combine held and suggested titles, deduplicate
            all_titles = []
            for title in result.get("held_titles", []) + result.get("suggested_titles", []):
                if title and title not in all_titles:
                    all_titles.append(title)

            return all_titles[:7]
    except Exception as e:
        print(f"LLM job title extraction failed: {e}")
        return []


def estimate_experience_years(text: str) -> Optional[int]:
    """Estimate years of experience from resume text."""
    import re

    # Look for patterns like "X years of experience" or "X+ years"
    patterns = [
        r"(\d+)\+?\s*years?\s+(?:of\s+)?experience",
        r"experience\s*[:\-]?\s*(\d+)\+?\s*years?",
        r"(\d+)\+?\s*years?\s+in\s+(?:software|development|engineering)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            years = int(match.group(1))
            if 0 < years < 50:  # Sanity check
                return years

    return None


@router.get("/", response_model=ResumeListResponse)
async def list_resume_profiles(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ResumeListResponse:
    """List all resume profiles."""
    # Get total count
    count_result = await fetch_one("SELECT COUNT(*) FROM resume_profiles")
    total = count_result["count"] if count_result else 0

    # Fetch profiles
    query = """
        SELECT id, name, description, is_default, file_path, skills,
               experience_years, experience_summary, target_titles,
               preferred_remote, preferred_locations,
               salary_expectation_min, salary_expectation_max,
               times_used, created_at, updated_at
        FROM resume_profiles
        ORDER BY is_default DESC, updated_at DESC
        LIMIT $1 OFFSET $2
    """
    records = await fetch_all(query, limit, offset)
    profiles = [ResumeProfileResponse(**record_to_dict(r)) for r in records]

    return ResumeListResponse(profiles=profiles, total=total)


@router.get("/{profile_id}", response_model=ResumeProfileDetailResponse)
async def get_resume_profile(profile_id: UUID) -> ResumeProfileDetailResponse:
    """Get a specific resume profile with all details."""
    query = """
        SELECT * FROM resume_profiles WHERE id = $1
    """
    record = await fetch_one(query, profile_id)

    if not record:
        raise HTTPException(status_code=404, detail="Resume profile not found")

    return ResumeProfileDetailResponse(**record_to_dict(record))


@router.post("/", response_model=ResumeProfileResponse)
async def create_resume_profile(
    profile: ResumeProfileCreate,
) -> ResumeProfileResponse:
    """Create a new resume profile without file upload."""
    # If setting as default, unset other defaults
    if profile.is_default:
        await execute("UPDATE resume_profiles SET is_default = FALSE WHERE is_default = TRUE")

    query = """
        INSERT INTO resume_profiles (
            name, description, is_default, skills, experience_years,
            experience_summary, target_titles, target_industries,
            preferred_remote, salary_expectation_min, salary_expectation_max
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING id, name, description, is_default, file_path, skills,
                  experience_years, experience_summary, target_titles,
                  preferred_remote, preferred_locations,
                  salary_expectation_min, salary_expectation_max,
                  times_used, created_at, updated_at
    """
    record = await fetch_one(
        query,
        profile.name,
        profile.description,
        profile.is_default,
        profile.skills,
        profile.experience_years,
        profile.experience_summary,
        profile.target_titles,
        profile.target_industries,
        profile.preferred_remote,
        profile.salary_expectation_min,
        profile.salary_expectation_max,
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create profile")

    return ResumeProfileResponse(**record_to_dict(record))


@router.post("/upload", response_model=ResumeProfileResponse)
async def upload_resume(
    file: UploadFile = File(..., description="PDF resume file"),
    name: str = Form(..., description="Profile name"),
    description: Optional[str] = Form(None, description="Profile description"),
    is_default: bool = Form(False, description="Set as default profile"),
) -> ResumeProfileResponse:
    """
    Upload a PDF resume and create a new profile.

    The resume will be parsed to extract:
    - Skills
    - Experience years
    - Text content for matching
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Calculate file hash
    file_hash = hashlib.sha256(content).hexdigest()

    # Extract text from PDF
    raw_text = extract_text_from_pdf(content)

    if not raw_text or len(raw_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. Please ensure it's not scanned/image-only."
        )

    # Extract skills, experience, and job titles using LLM
    skills = await extract_skills_from_text_llm(raw_text)
    experience_years = estimate_experience_years(raw_text)
    target_titles = await extract_job_titles_from_resume(raw_text)

    # If setting as default, unset other defaults
    if is_default:
        await execute("UPDATE resume_profiles SET is_default = FALSE WHERE is_default = TRUE")

    # Save to database (including PDF binary for viewing)
    query = """
        INSERT INTO resume_profiles (
            name, description, is_default, file_hash, raw_text,
            skills, experience_years, target_titles, file_content, last_file_updated
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        RETURNING id, name, description, is_default, file_path, skills,
                  experience_years, experience_summary, target_titles,
                  preferred_remote, preferred_locations,
                  salary_expectation_min, salary_expectation_max,
                  times_used, created_at, updated_at
    """
    record = await fetch_one(
        query,
        name,
        description,
        is_default,
        file_hash,
        raw_text,
        skills,
        experience_years,
        target_titles,
        content,  # Store the PDF binary
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to save profile")

    return ResumeProfileResponse(**record_to_dict(record))


@router.put("/{profile_id}", response_model=ResumeProfileResponse)
async def update_resume_profile(
    profile_id: UUID,
    update: ResumeProfileUpdate,
) -> ResumeProfileResponse:
    """Update a resume profile."""
    # Check if profile exists
    existing = await fetch_one("SELECT id FROM resume_profiles WHERE id = $1", profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Resume profile not found")

    # If setting as default, unset other defaults
    if update.is_default:
        await execute(
            "UPDATE resume_profiles SET is_default = FALSE WHERE is_default = TRUE AND id != $1",
            profile_id
        )

    # Build dynamic update query
    updates = []
    params = []
    param_idx = 1

    fields = {
        "name": update.name,
        "description": update.description,
        "is_default": update.is_default,
        "skills": update.skills,
        "experience_years": update.experience_years,
        "experience_summary": update.experience_summary,
        "target_titles": update.target_titles,
        "target_industries": update.target_industries,
        "preferred_remote": update.preferred_remote,
        "preferred_locations": update.preferred_locations,
        "salary_expectation_min": update.salary_expectation_min,
        "salary_expectation_max": update.salary_expectation_max,
    }

    for field, value in fields.items():
        if value is not None:
            updates.append(f"{field} = ${param_idx}")
            params.append(value)
            param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(profile_id)
    query = f"""
        UPDATE resume_profiles
        SET {", ".join(updates)}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING id, name, description, is_default, file_path, skills,
                  experience_years, experience_summary, target_titles,
                  preferred_remote, preferred_locations,
                  salary_expectation_min, salary_expectation_max,
                  times_used, created_at, updated_at
    """

    record = await fetch_one(query, *params)

    if not record:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    return ResumeProfileResponse(**record_to_dict(record))


@router.delete("/{profile_id}")
async def delete_resume_profile(profile_id: UUID) -> dict[str, str]:
    """Delete a resume profile."""
    result = await execute("DELETE FROM resume_profiles WHERE id = $1", profile_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Resume profile not found")

    return {"status": "deleted", "id": str(profile_id)}


@router.post("/{profile_id}/generate-titles")
async def generate_titles_from_resume(profile_id: UUID) -> dict[str, Any]:
    """
    Generate job title suggestions from existing resume text using AI.
    Returns both held titles and suggested titles for job search.
    """
    # Get the resume's raw text
    query = "SELECT raw_text FROM resume_profiles WHERE id = $1"
    record = await fetch_one(query, profile_id)

    if not record:
        raise HTTPException(status_code=404, detail="Resume profile not found")

    raw_text = record.get("raw_text")
    if not raw_text:
        raise HTTPException(
            status_code=400,
            detail="No resume text available. Please upload a PDF resume first."
        )

    # Generate titles using LLM
    titles = await extract_job_titles_from_resume(raw_text)

    return {
        "profile_id": str(profile_id),
        "titles": titles,
    }


@router.get("/{profile_id}/text")
async def get_resume_text(profile_id: UUID) -> dict[str, Any]:
    """Get the raw text extracted from the resume."""
    query = "SELECT raw_text, skills, experience_years FROM resume_profiles WHERE id = $1"
    record = await fetch_one(query, profile_id)

    if not record:
        raise HTTPException(status_code=404, detail="Resume profile not found")

    return {
        "id": str(profile_id),
        "raw_text": record.get("raw_text"),
        "skills": record.get("skills"),
        "experience_years": record.get("experience_years"),
    }


@router.get("/{profile_id}/pdf")
async def get_resume_pdf(profile_id: UUID):
    """Download or view the original PDF resume."""
    from fastapi.responses import Response

    query = "SELECT name, file_content FROM resume_profiles WHERE id = $1"
    record = await fetch_one(query, profile_id)

    if not record:
        raise HTTPException(status_code=404, detail="Resume profile not found")

    file_content = record.get("file_content")
    if not file_content:
        raise HTTPException(
            status_code=404,
            detail="No PDF file stored for this resume. Re-upload to enable PDF viewing."
        )

    # Convert memoryview to bytes if needed
    if isinstance(file_content, memoryview):
        file_content = bytes(file_content)

    filename = f"{record.get('name', 'resume').replace(' ', '_')}.pdf"

    return Response(
        content=file_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        }
    )
