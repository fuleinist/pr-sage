"""Tests for truncation helpers."""

from pr_sage.truncation import head_tail, truncate_bytes


def test_truncate_bytes_no_op_when_small():
    text, truncated = truncate_bytes("hello", 100)
    assert text == "hello"
    assert truncated is False


def test_truncate_bytes_marks_truncation():
    text, truncated = truncate_bytes("x" * 500, 100)
    assert truncated is True
    assert "[truncated" in text
    assert text.startswith("x" * 100)


def test_truncate_bytes_zero_budget():
    text, truncated = truncate_bytes("data", 0)
    assert text == ""
    assert truncated is True


def test_head_tail_keeps_both_ends():
    text = "HEAD" + "m" * 1000 + "TAIL"
    out, truncated = head_tail(text, 50, 50)
    assert truncated is True
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "[truncated" in out


def test_head_tail_no_op_when_small():
    out, truncated = head_tail("short", 50, 50)
    assert out == "short"
    assert truncated is False
