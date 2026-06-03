"""Unit tests for the config-driven candidate profile (and the no-PII guarantee)."""

import utils.profile as profile

_FORBIDDEN = ("Josh", "Spadaro", "508-314", "IPG", "joshua.s.spadaro", "kynthar")


def test_candidate_name_and_first_name():
    assert profile.candidate_name()
    first = profile.candidate_first_name()
    assert first and " " not in first


def test_signatures_built_from_profile_and_pii_free():
    name = profile.candidate_name()
    for style in ("default", "email", "formal"):
        sig = profile.build_signature(style)
        assert sig and name in sig

    blob = (
        " ".join(profile.build_signature(s) for s in ("default", "email", "formal"))
        + str(profile.load_profile())
        + profile.build_html_signature()
    )
    for bad in _FORBIDDEN:
        assert bad not in blob


def test_resume_dict_shape():
    resume = profile.resume_dict()
    for key in ("name", "titles", "skills", "years_of_experience", "preferences"):
        assert key in resume
    assert isinstance(resume["skills"], dict)


def test_matching_config_is_generic():
    boost = profile.boost_skills()
    assert boost and all(s == s.lower() for s in boost)
    metros = profile.metro_areas()
    assert isinstance(metros, dict)

    blob = " ".join(boost) + " " + " ".join(profile.domain_keywords()) + " " + " ".join(metros)
    for personal in ("supply chain", "mrp", "bom", "boston", "natick", "marlborough"):
        assert personal not in blob
