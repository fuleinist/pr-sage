"""ContextBuilder tests against a fake GitHub client (no network)."""

from pr_sage.context import ContextBuilder, PRRef
from pr_sage.github_client import GitHubError

REF = PRRef(owner="octo", repo="demo", number=5)

PR = {
    "title": "Fix cache invalidation bug",
    "body": "Fixes #12 — stale entries were served after writes.",
    "user": {"login": "alice"},
    "base": {"ref": "main"},
    "head": {"ref": "fix-cache", "sha": "abc123"},
    "labels": [{"name": "bug"}],
    "changed_files": 2,
    "additions": 30,
    "deletions": 4,
    "html_url": "https://github.com/octo/demo/pull/5",
}

FILES = [
    {"filename": "cache.py", "status": "modified", "additions": 20, "deletions": 4},
    {"filename": "old.py", "status": "removed", "additions": 0, "deletions": 10},
    {"filename": "new.py", "status": "added", "additions": 10, "deletions": 0},
]

COMMITS = [
    {"commit": {"message": "invalidate on write\n\nLong body ignored"}},
    {"commit": {"message": "add regression test"}},
]

ISSUE_12 = {
    "title": "Cache serves stale entries",
    "body": "Repro: write then read.",
    "state": "open",
    "html_url": "https://github.com/octo/demo/issues/12",
}

REVIEWS = [{"user": {"login": "bob"}, "body": "Please add tests.", "submitted_at": "2026-09-20"}]
REVIEW_COMMENTS = [
    {"user": {"login": "bob"}, "body": "nit: naming", "path": "cache.py", "line": 10,
     "created_at": "2026-09-20"}
]
ISSUE_COMMENTS = [{"user": {"login": "alice"}, "body": "Updated.", "created_at": "2026-09-21"}]

FILE_CONTENTS = {
    "cache.py": "class Cache:\n    pass\n",
    "new.py": "def helper():\n    return 1\n",
}


class FakeClient:
    def __init__(self, *, fail_comments: bool = False, issue_is_pr: bool = False):
        self.fail_comments = fail_comments
        self.issue_is_pr = issue_is_pr
        self.fetched_paths: list[str] = []

    def get_pr(self, o, r, n):
        return PR

    def get_pr_diff(self, o, r, n):
        return "diff --git a/cache.py b/cache.py\n+new line\n"

    def get_pr_files(self, o, r, n):
        return FILES

    def get_pr_commits(self, o, r, n):
        return COMMITS

    def get_file_content(self, o, r, path, ref):
        self.fetched_paths.append(path)
        return FILE_CONTENTS.get(path)

    def get_issue(self, o, r, n):
        if self.issue_is_pr:
            return {**ISSUE_12, "pull_request": {"url": "..."}}
        return ISSUE_12

    def get_reviews(self, o, r, n):
        if self.fail_comments:
            raise GitHubError("403")
        return REVIEWS

    def get_review_comments(self, o, r, n):
        if self.fail_comments:
            raise GitHubError("403")
        return REVIEW_COMMENTS

    def get_issue_comments(self, o, r, n):
        if self.fail_comments:
            raise GitHubError("403")
        return ISSUE_COMMENTS


def test_build_full_context():
    fake = FakeClient()
    ctx = ContextBuilder(fake).build(REF)
    assert ctx.meta.title == PR["title"]
    assert ctx.meta.head_sha == "abc123"
    assert ctx.meta.labels == ["bug"]
    assert ctx.diff.startswith("diff --git")
    assert ctx.diff_truncated is False
    # removed file fetches no content
    assert "old.py" not in fake.fetched_paths
    by_path = {f.path: f for f in ctx.files}
    assert by_path["cache.py"].content.startswith("class Cache")
    assert by_path["old.py"].content == ""
    assert by_path["new.py"].content
    # issue #12 extracted from PR body
    assert [i.number for i in ctx.issues] == [12]
    assert ctx.issues[0].title == ISSUE_12["title"]
    # commits: first line only
    assert ctx.commit_messages == ["invalidate on write", "add regression test"]
    # comments: reviews + review comments + issue comments
    kinds = [c.kind for c in ctx.comments]
    assert kinds == ["review", "review_comment", "issue_comment"]
    assert ctx.comments[1].path == "cache.py"
    assert ctx.comments[1].line == 10


def test_file_cap_respected():
    ctx = ContextBuilder(FakeClient(), max_files=2).build(REF)
    assert len(ctx.files) == 2


def test_file_content_truncation_marker():
    class BigClient(FakeClient):
        def get_file_content(self, o, r, path, ref):
            return "x" * 10_000

    ctx = ContextBuilder(BigClient(), max_file_bytes=500).build(REF)
    big = next(f for f in ctx.files if f.path == "cache.py")
    assert big.truncated is True
    assert "[truncated" in big.content


def test_diff_truncation_head_tail():
    class BigDiff(FakeClient):
        def get_pr_diff(self, o, r, n):
            return "D" * 100_000

    ctx = ContextBuilder(BigDiff(), max_diff_bytes=1000).build(REF)
    assert ctx.diff_truncated is True
    assert "[truncated" in ctx.diff
    assert len(ctx.diff) < 1200


def test_self_pr_reference_skipped():
    class SelfRef(FakeClient):
        pass

    pr = {**PR, "body": "Follow-up to #5 itself and fixes #12"}
    SelfRef.get_pr = lambda self, o, r, n: pr  # type: ignore[method-assign]
    ctx = ContextBuilder(SelfRef()).build(REF)
    assert [i.number for i in ctx.issues] == [12]


def test_issue_that_is_a_pr_skipped():
    ctx = ContextBuilder(FakeClient(issue_is_pr=True)).build(REF)
    assert ctx.issues == []


def test_comment_fetch_failures_degrade_gracefully():
    ctx = ContextBuilder(FakeClient(fail_comments=True)).build(REF)
    assert ctx.comments == []
    assert ctx.meta.title == PR["title"]  # rest of the context survives


def test_comment_cap_and_truncation():
    class Chatty(FakeClient):
        def get_issue_comments(self, o, r, n):
            return [
                {"user": {"login": f"u{i}"}, "body": "y" * 5000, "created_at": ""}
                for i in range(40)
            ]

    ctx = ContextBuilder(Chatty(), max_comments=10, max_comment_bytes=100).build(REF)
    assert len(ctx.comments) == 10
    # first two entries are the short review + review_comment from FakeClient;
    # the remaining issue comments are oversized and must carry markers
    long_ones = [c for c in ctx.comments if c.kind == "issue_comment"]
    assert long_ones, "expected chatty issue comments in context"
    for c in long_ones:
        assert "[truncated" in c.body
