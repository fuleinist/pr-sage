"""Tests for PR reference parsing and issue-reference extraction."""

import pytest

from pr_sage.context import RefParseError, extract_issue_refs, parse_pr_ref


def test_parse_hash_form():
    ref = parse_pr_ref("octocat/hello-world#42")
    assert (ref.owner, ref.repo, ref.number) == ("octocat", "hello-world", 42)


def test_parse_pull_path_form():
    ref = parse_pr_ref("octocat/hello-world/pull/7")
    assert (ref.owner, ref.repo, ref.number) == ("octocat", "hello-world", 7)


def test_parse_url_form():
    ref = parse_pr_ref("https://github.com/foo/bar/pull/123")
    assert (ref.owner, ref.repo, ref.number) == ("foo", "bar", 123)


def test_parse_url_with_query_and_fragment():
    # trailing junk after the number is tolerated by the regex boundary
    ref = parse_pr_ref("https://github.com/foo/bar/pull/123#issuecomment-1")
    assert ref.number == 123


def test_parse_invalid():
    for bad in ["", "nonsense", "owner/repo", "#42", "owner/repo##3"]:
        with pytest.raises(RefParseError):
            parse_pr_ref(bad)


def test_extract_issue_refs_keyword_forms():
    text = "Fixes #12, closes #34 and refers to #56"
    assert extract_issue_refs(text) == [12, 34, 56]


def test_extract_issue_refs_bare_and_url():
    text = "Related to #99 and https://github.com/o/r/issues/100"
    assert extract_issue_refs(text) == [99, 100]


def test_extract_issue_refs_dedup_preserves_order():
    assert extract_issue_refs("#5 #3 #5 #3 #8") == [5, 3, 8]


def test_extract_issue_refs_empty():
    assert extract_issue_refs("") == []
    assert extract_issue_refs("no refs here") == []
