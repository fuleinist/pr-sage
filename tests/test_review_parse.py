"""Review JSON parser tests: fences, prose wrapping, malformed payloads."""

import json

from pr_sage.review import extract_json, parse_review, render_markdown

VALID = {
    "summary": "Solid PR with one blocking issue.",
    "strengths": ["Clear naming", "Good test coverage"],
    "concerns": [
        {"severity": "blocking", "message": "SQL injection in query builder",
         "file": "db.py", "line": 42},
        {"severity": "nit", "message": "Trailing whitespace"},
    ],
    "suggestions": [
        {"file": "db.py", "line": 42, "body": "Use parameterized queries"}
    ],
    "verdict": "request-changes",
}


def test_parse_clean_json():
    review = parse_review(json.dumps(VALID))
    assert review.structured is True
    assert review.summary == VALID["summary"]
    assert len(review.concerns) == 2
    assert review.concerns[0].severity == "blocking"
    assert review.concerns[0].file == "db.py"
    assert review.concerns[0].line == 42
    assert review.concerns[1].line is None
    assert review.suggestions[0].body.startswith("Use parameterized")
    assert review.verdict == "request-changes"


def test_parse_fenced_json():
    raw = "Here is my review:\n```json\n" + json.dumps(VALID) + "\n```\nThanks!"
    review = parse_review(raw)
    assert review.structured is True
    assert review.summary == VALID["summary"]


def test_parse_prose_wrapped_json():
    raw = "Sure! " + json.dumps(VALID) + " Hope that helps."
    review = parse_review(raw)
    assert review.structured is True


def test_extract_json_prefers_fence():
    raw = 'noise {"not": "it"} ```json\n{"real": 1}\n```'
    assert json.loads(extract_json(raw)) == {"real": 1}


def test_parse_malformed_falls_back_unstructured():
    review = parse_review("this is not json at all {broken")
    assert review.structured is False
    assert "not json" in review.raw


def test_parse_uses_repaired_candidate():
    review = parse_review("garbage", json.dumps(VALID))
    assert review.structured is True
    assert review.summary == VALID["summary"]


def test_parse_tolerates_string_concerns():
    raw = json.dumps({"summary": "s", "concerns": ["plain string concern"], "verdict": "comment"})
    review = parse_review(raw)
    assert review.structured is True
    assert review.concerns[0].message == "plain string concern"


def test_render_markdown_structured():
    review = parse_review(json.dumps(VALID))
    out = render_markdown(review, "o/r#1 — Title")
    assert "o/r#1" in out
    assert "[BLOCKING]" in out
    assert "db.py:42" in out
    assert "REQUEST CHANGES" in out


def test_render_markdown_unstructured():
    review = parse_review("freeform text review")
    out = render_markdown(review)
    assert "Unstructured review" in out
    assert "freeform text review" in out
