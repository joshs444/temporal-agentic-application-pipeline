"""Unit tests for the fast job-matching pre-filter (pure functions, no I/O)."""

from utils.matching import (
    calculate_quick_score,
    experience_level_match,
    extract_salary_from_text,
    keyword_match_score,
    location_match,
    salary_match,
    title_match_score,
)


def test_keyword_match_score_bounds_and_signal():
    assert keyword_match_score("", ["python"]) == 0.0
    assert keyword_match_score("We use Python", []) == 0.0

    strong = keyword_match_score(
        "Senior Python engineer building FastAPI and Temporal services",
        ["Python", "FastAPI", "Temporal"],
    )
    weak = keyword_match_score("We use Java and Spring", ["Python", "FastAPI", "Temporal"])
    assert 0.0 < strong <= 1.0
    assert weak < strong


def test_experience_level_match():
    assert experience_level_match("Senior Engineer", 6) == 1.0          # in 5-10 range
    assert experience_level_match("Senior Engineer", 0) < 0.5           # underqualified
    assert experience_level_match("Junior Engineer", 1) == 1.0          # in 0-2 range
    assert 0.0 <= experience_level_match("Staff Engineer", 30) <= 1.0   # overqualified, clamped


def test_location_match_remote_and_onsite():
    assert location_match("Remote", "Anywhere", True, "remote") == 1.0
    assert location_match("Remote", "NYC", False, "remote") == 0.5


def test_salary_match():
    assert salary_match((None, None), (150000, 200000)) == 0.5          # unknown -> neutral
    assert salary_match((210000, 260000), (150000, 200000)) == 1.0      # pays above expectation
    low = salary_match((80000, 90000), (150000, 200000))
    assert 0.0 <= low < 0.5                                             # well below expectation


def test_title_match_score():
    assert title_match_score("Senior Software Engineer", ["Software Engineer"]) == 1.0
    assert title_match_score("", ["Software Engineer"]) == 0.5
    assert (
        title_match_score("Barista", ["Software Engineer"])
        < title_match_score("Staff Engineer", ["Software Engineer"])
    )


def test_extract_salary_from_text():
    assert extract_salary_from_text("$150,000 - $200,000 per year") == (150000, 200000)
    assert extract_salary_from_text("competitive salary") == (None, None)
    assert extract_salary_from_text("") == (None, None)


def test_calculate_quick_score_shape():
    job = {
        "title": "Senior Python Engineer",
        "description": "Build FastAPI + Temporal services",
        "location": "Remote",
        "remote_type": "remote",
        "salary_min": 180000,
        "salary_max": 220000,
    }
    resume = {
        "skills": {"backend": ["Python", "FastAPI", "Temporal"]},
        "years_of_experience": 6,
        "location": "Remote",
        "preferences": {
            "target_roles": ["Software Engineer"],
            "work_types": ["remote"],
            "salary_expectation": {"min": 150000, "max": 250000},
        },
    }
    out = calculate_quick_score(job, resume)
    assert 0.0 <= out["quick_score"] <= 100.0
    assert "components" in out and "keyword_match" in out["components"]
