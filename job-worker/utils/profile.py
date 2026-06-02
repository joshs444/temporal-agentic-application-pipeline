"""Candidate profile loading.

The pipeline is candidate-agnostic: every personal detail (name, contact info,
background, resume) lives in a YAML profile file, never in source code. This is
what keeps the codebase shareable and the operator's identity out of git.

Resolution order (first match wins):

    1. $PROFILE_PATH                     explicit override
    2. ./data/profile.yaml               your real profile (gitignored)
    3. ./profile.yaml                    your real profile (gitignored)
    4. ./profile.example.yaml            the checked-in placeholder template
    5. built-in generic defaults         so the app always runs

To customize, copy ``profile.example.yaml`` to ``profile.yaml`` (or
``data/profile.yaml``) and edit it, or set ``PROFILE_PATH``. The example file is
the schema reference.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Built-in fallback so the pipeline runs even with no profile file present.
# Deliberately generic — real details belong in a gitignored profile.yaml.
_DEFAULT_PROFILE: dict[str, Any] = {
    "candidate": {
        "name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "phone": "+1 (555) 010-0100",
        "linkedin": "linkedin.com/in/example",
        "location": "Remote (US)",
        "headline": "Senior Software Engineer",
        "current_company": "Acme Corp",
        "years_experience": 6,
    },
    "background": [
        "Builds production-grade backend and AI/agentic systems end to end",
        "Comfortable across Python, distributed systems, and workflow orchestration",
        "Ships measurable impact through automation, reliability, and tooling",
    ],
    "achievements": [
        "Designed and shipped a durable, fault-tolerant automation pipeline in production",
        "Integrated several third-party APIs into a single orchestrated workflow",
        "Deployed ML/LLM features to production with measurable ROI",
    ],
    "resume": {
        "titles": ["Senior Software Engineer", "Staff Engineer"],
        "summary": "Engineer focused on reliable automation and production AI systems.",
        "years_of_experience": 6,
        "skills": {
            "ai_automation": ["LLM integration", "Agentic workflows", "Prompt engineering"],
            "backend": ["Python", "FastAPI", "PostgreSQL", "Temporal"],
            "frontend": ["JavaScript", "HTML", "CSS"],
            "other": ["Docker", "AWS", "CI/CD"],
        },
        "experience": [
            {
                "title": "Senior Software Engineer",
                "company": "Acme Corp",
                "highlights": [
                    "Built a durable workflow pipeline orchestrating LLM + external APIs",
                    "Reduced manual processing time through end-to-end automation",
                ],
            }
        ],
        "education": [
            {"degree": "B.S.", "field": "Computer Science", "institution": "State University"}
        ],
    },
}


def _candidate_paths() -> list[Path]:
    """Build the ordered list of profile file locations to probe."""
    candidates: list[Path] = []

    env_path = os.getenv("PROFILE_PATH")
    if env_path:
        candidates.append(Path(env_path))

    # In-container app root (/app), repo root in a local checkout, and CWD.
    here = Path(__file__).resolve()
    roots = {here.parents[1], Path("/app"), Path.cwd()}
    try:
        roots.add(here.parents[2])  # repo root when running from a checkout
    except IndexError:
        pass

    for root in roots:
        candidates.append(root / "data" / "profile.yaml")
        candidates.append(root / "profile.yaml")
        candidates.append(root / "profile.example.yaml")

    return candidates


@functools.lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    """Load the candidate profile, falling back to built-in generic defaults.

    Never raises: a missing or malformed file logs a warning and yields the
    built-in default profile so the pipeline always runs and never leaks PII.
    """
    for path in _candidate_paths():
        try:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict) and data.get("candidate"):
                    log.info("Loaded candidate profile from %s", path)
                    return data
        except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - defensive
            log.warning("Failed to read profile %s: %s", path, exc)

    log.info("No profile file found; using built-in generic defaults")
    return _DEFAULT_PROFILE


def candidate() -> dict[str, Any]:
    """Return the ``candidate`` block (name, contact info, headline, ...)."""
    return load_profile().get("candidate", _DEFAULT_PROFILE["candidate"])


def candidate_name() -> str:
    """Full name of the candidate."""
    return candidate().get("name", "")


def candidate_first_name() -> str:
    """First name of the candidate (used as an email sign-off)."""
    name = candidate_name().strip()
    return name.split()[0] if name else ""


def background_lines() -> list[str]:
    """Background bullets injected into cover-letter / outreach system prompts."""
    return load_profile().get("background", [])


def achievements() -> list[str]:
    """Concrete achievements the resume-tailoring prompt can draw from."""
    return load_profile().get("achievements", [])


def background_block() -> str:
    """Render the background bullets as a prompt-ready bullet list."""
    return "\n".join(f"- {line}" for line in background_lines())


def achievements_block() -> str:
    """Render the achievements as a prompt-ready bullet list."""
    return "\n".join(f"- {line}" for line in achievements())


def build_signature(style: str = "default") -> str:
    """Build an email/letter signature block from the candidate profile.

    Args:
        style: ``"default"`` / ``"formal"`` (closing + full block) or
            ``"email"`` (casual first-name sign-off + contact block).
    """
    c = candidate()
    name = c.get("name", "")
    phone = c.get("phone", "")
    email = c.get("email", "")
    linkedin = c.get("linkedin", "")
    contact_lines = [line for line in (phone, email, linkedin) if line]

    if style == "email":
        closing = f"Best,\n{candidate_first_name()}"
        block = "\n".join([name, *contact_lines])
        return f"{closing}\n\n---\n{block}"

    closing = "Sincerely," if style == "formal" else "Best regards,"
    return "\n".join([closing, name, *contact_lines])


def build_html_signature() -> str:
    """Build an HTML signature block from the candidate profile."""
    c = candidate()
    name = c.get("name", "")
    phone = c.get("phone", "")
    linkedin = c.get("linkedin", "")
    linkedin_url = linkedin if linkedin.startswith("http") else f"https://{linkedin}"
    return f"""
<table cellpadding="0" cellspacing="0" border="0" style="margin-top: 16px; font-family: Arial, sans-serif;">
  <tr>
    <td style="padding-bottom: 8px;">
      <span style="font-size: 14px; color: #1d1d1f; font-weight: 600;">{name}</span>
    </td>
  </tr>
  <tr>
    <td style="border-top: 2px solid #3b82f6; padding-top: 8px;">
      <table cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
            <span style="font-size: 12px; color: #636366;">{phone}</span>
            <span style="font-size: 12px; color: #d2d2d7;"> | </span>
            <a href="{linkedin_url}" style="font-size: 12px; color: #3b82f6; text-decoration: none;">LinkedIn</a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""


def resume_dict() -> dict[str, Any]:
    """Return a resume in the structure the matching pipeline expects.

    Used as the fallback when no default resume profile exists in the database.
    Merges candidate identity with the ``resume`` block of the profile.
    """
    profile = load_profile()
    c = profile.get("candidate", {})
    resume = dict(profile.get("resume", {}))

    resume.setdefault("name", c.get("name", ""))
    resume.setdefault("email", c.get("email", ""))
    resume.setdefault("location", c.get("location", ""))
    resume.setdefault("years_of_experience", c.get("years_experience", 0))
    resume.setdefault("achievements", profile.get("achievements", []))
    resume.setdefault(
        "preferences",
        {
            "target_roles": resume.get("titles", []),
            "industries": [],
            "work_types": ["remote", "hybrid"],
            "salary_expectation": {"min": 0, "max": 999999, "currency": "USD"},
        },
    )
    return resume
