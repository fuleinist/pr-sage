"""Prompt construction + GitHub review-body builder + CLI echo/dry-run paths."""

import json

import pytest

from pr_sage.cli import EXIT_OK, EXIT_USAGE, main
from pr_sage.github_client import build_review_body_markdown
from pr_sage.models import (
    CommentContext,
    Concern,
    FileContext,
    IssueContext,
    PRMeta,
    Review,
    ReviewContext,
    Suggestion,
)
from pr_sage.prompts import SYSTEM_PROMPT, build_user_prompt, repair_prompt


def make_ctx() -> ReviewContext:
    return ReviewContext(
        meta=PRMeta(
            owner="o", repo="r", number=1, title="Add feature",
            body="Closes #2", author="alice", base="main", head="feat",
            labels=["enhancement"], changed_files=1, additions=10, deletions=0,
            url="https://github.com/o/r/pull/1",
        ),
        diff="@@ -1 +1,2 @@\n+feature",
        files=[FileContext(path="feat.py", status="added", additions=10, content="def f(): ...")],
        issues=[IssueContext(number=2, title="Want feature", body="Please", state="open")],
        comments=[CommentContext(author="bob", body="lgtm so far", kind="review")],
        commit_messages=["add feature"],
    )


def test_user_prompt_contains_all_sections():
    prompt = build_user_prompt(make_ctx())
    assert "## PULL REQUEST" in prompt
    assert "Add feature" in prompt
    assert "## COMMITS" in prompt
    assert "## RELATED ISSUES" in prompt
    assert "Issue #2" in prompt
    assert "## DIFF" in prompt
    assert "+feature" in prompt
    assert "## FULL FILE CONTENTS" in prompt
    assert "feat.py" in prompt
    assert "## PRIOR REVIEW HISTORY" in prompt
    assert "bob" in prompt
    assert "strict-JSON" in prompt


def test_system_prompt_contract():
    assert "blocking" in SYSTEM_PROMPT
    assert "verdict" in SYSTEM_PROMPT
    assert "At most 3 nits" in SYSTEM_PROMPT


def test_repair_prompt_embeds_previous():
    out = repair_prompt("garbage output")
    assert "garbage output" in out
    assert "JSON" in out


def test_review_body_markdown():
    review = Review(
        summary="Overall good.",
        strengths=["clean"],
        concerns=[Concern(severity="should-fix", message="missing edge case", file="a.py", line=5)],
        suggestions=[Suggestion(file="a.py", line=5, body="handle None")],
        verdict="comment",
    )
    body = build_review_body_markdown(review)
    assert "PR-Sage review" in body
    assert "Overall good." in body
    assert "**should-fix**" in body
    assert "`a.py:5`" in body
    assert "**Verdict:** comment" in body


def test_cli_bad_ref_exits_2(capsys):
    code = main(["review", "not-a-ref"])
    assert code == EXIT_USAGE
    assert "Cannot parse" in capsys.readouterr().err


def test_cli_review_requires_repo_and_pr_together():
    assert main(["review", "--repo", "o/r"]) == EXIT_USAGE


class FakeClient:
    token = "fake"

    def __getattr__(self, name):
        def method(*a, **k):
            if name == "get_pr":
                return {
                    "title": "T", "body": "", "user": {"login": "a"},
                    "base": {"ref": "main"}, "head": {"ref": "h", "sha": "s"},
                    "labels": [], "changed_files": 0, "additions": 0,
                    "deletions": 0, "html_url": "u",
                }
            if name == "get_pr_diff":
                return "diff"
            if name in ("get_pr_files", "get_pr_commits", "get_issue_comments",
                        "get_review_comments", "get_reviews"):
                return []
            raise AssertionError(f"unexpected call {name}")

        return method


def test_cli_echo_review_end_to_end(monkeypatch, capsys):
    """echo provider + fake GitHubClient => full CLI path, no network."""
    import pr_sage.cli as cli

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)
    code = main(["review", "o/r#1", "--provider", "echo"])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Echo provider review" in out
    assert "Verdict: COMMENT" in out


def test_cli_echo_json_mode(monkeypatch, capsys):
    import pr_sage.cli as cli

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)
    code = main(["review", "o/r#1", "--provider", "echo", "--json"])
    assert code == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["structured"] is True
    assert data["verdict"] == "comment"
    assert "raw" not in data


def test_cli_dry_run_skips_llm(monkeypatch, capsys):
    import pr_sage.cli as cli

    monkeypatch.setattr(cli, "GitHubClient", FakeClient)

    def no_provider(name):
        raise AssertionError("dry-run must not build a provider")

    monkeypatch.setattr(cli, "get_provider", no_provider)
    code = main(["review", "o/r#1", "--dry-run"])
    assert code == EXIT_OK
    assert "prompt size" in capsys.readouterr().out
