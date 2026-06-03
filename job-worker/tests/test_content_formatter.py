"""Unit tests for content formatting + validation helpers."""

from utils.content_formatter import (
    clean_subject_line,
    clean_text,
    validate_cover_letter,
    validate_email,
    word_count,
)


def test_clean_text_strips_artifacts_and_whitespace():
    assert clean_text("Here is the cover letter:\n\nHello") == "Hello"
    assert clean_text("a\n\n\n\nb") == "a\n\nb"
    assert clean_text("  spaced   out  ") == "spaced out"


def test_clean_subject_line():
    assert clean_subject_line("Subject: Hello") == "Hello"
    assert clean_subject_line('"Quoted"') == "Quoted"
    long = clean_subject_line("x" * 80)
    assert len(long) <= 60


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_validate_cover_letter_flags_ai_speak_and_length():
    ok, issues = validate_cover_letter(
        "I led a team that shipped a platform serving 10000 requests per day. "
        "We cut latency by 40 percent.\n\n"
        "I built durable pipelines on Temporal that reduced manual work.\n\n"
        "I would welcome the chance to bring that to your team and discuss next steps."
    )
    assert isinstance(ok, bool) and isinstance(issues, list)

    bad_ok, bad_issues = validate_cover_letter("I am excited to apply and leverage synergy.")
    assert bad_ok is False
    assert any("AI-speak" in i for i in bad_issues)


def test_validate_email_checks_ask_and_length():
    ok, issues = validate_email(
        "Quick question about the role",
        "Hi there, I built durable agentic pipelines on Temporal and recently shipped an "
        "LLM-powered matching service end to end. I would love to learn more about what "
        "your team is building. Would you have fifteen minutes for a quick call this week?",
    )
    assert ok is True and issues == []

    no_ask_ok, no_ask_issues = validate_email("Hi", "I exist.")
    assert no_ask_ok is False
