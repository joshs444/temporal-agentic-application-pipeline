"""Unit tests for the resilient LLM JSON extractor."""

from utils.llm import extract_json


def test_extract_json_handles_common_shapes():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json("Sure! Here you go:\n```\n{\"a\": 3}\n```") == {"a": 3}
    assert extract_json('prefix {"a": 4} suffix') == {"a": 4}
    assert extract_json("[1, 2, 3]") == [1, 2, 3]


def test_extract_json_degrades_gracefully():
    assert extract_json("not json at all") == {}
    assert extract_json("") == {}
    assert extract_json(None) == {}
