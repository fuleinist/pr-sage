"""Context assembly: parse PR references and build the ReviewContext."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .github_client import GitHubClient, GitHubError
from .models import (
    CommentContext,
    FileContext,
    IssueContext,
    PRMeta,
    ReviewContext,
)
from .truncation import head_tail, truncate_bytes


class RefParseError(ValueError):
    """Raised when a PR reference cannot be parsed."""


@dataclass
class PRRef:
    owner: str
    repo: str
    number: int


_REF_PATTERNS = [
    # https://github.com/owner/repo/pull/123 (any host segment tolerated)
    re.compile(r"https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)"),
    # owner/repo/pull/123
    re.compile(r"^([\w.-]+)/([\w.-]+)/pull/(\d+)$"),
    # owner/repo#123
    re.compile(r"^([\w.-]+)/([\w.-])#(\d+)$"),
]


def parse_pr_ref(ref: str) -> PRRef:
    """Parse the four supported PR reference forms (SPEC FR-1)."""
    ref = ref.strip()
    for pattern in _REF_PATTERNS:
        m = pattern.match(ref)
        if m:
            return PRRef(owner=m.group(1), repo=m.group(2), number=int(m.group(3)))
    raise RefParseError(
        f"Cannot parse PR reference {ref!r}. Expected one of: "
        "owner/repo#123, owner/repo/pull/123, https://github.com/owner/repo/pull/123"
    )


_ISSUE_REF_RE = re.compile(
    r"(?:\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?|ref[s]?)\s+)?#(\d{1,6})\b"
)
_ISSUE_URL_RE = re.compile(r"https?://[^/]+/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)")


def extract_issue_refs(text: str) -> list[int]:
    """Find referenced issue numbers in free text (dedup, order-preserved)."""
    seen: dict[int, None] = {}
    for m in _ISSUE_REF_RE.finditer(text or ""):
        seen.setdefault(int(m.group(1)), None)
    for m in _ISSUE_URL_RE.finditer(text or ""):
        seen.setdefault(int(m.group(3)), None)
    return list(seen)


class ContextBuilder:
    """Assembles a ReviewContext from the GitHub API within byte budgets."""

    def __init__(
        self,
        client: GitHubClient,
        *,
        max_files: int = 12,
        max_file_bytes: int = 24 * 1024,
        max_diff_bytes: int = 48 * 1024,
        max_issues: int = 5,
        max_issue_bytes: int = 8 * 1024,
        max_comments: int = 20,
        max_comment_bytes: int = 2 * 1024,
        max_commits: int = 20,
    ):
        self.client = client
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_diff_bytes = max_diff_bytes
        self.max_issues = max_issues
        self.max_issue_bytes = max_issue_bytes
        self.max_comments = max_comments
        self.max_comment_bytes = max_comment_bytes
        self.max_commits = max_commits

    def build(self, ref: PRRef) -> ReviewContext:
        c = self.client
        pr = c.get_pr(ref.owner, ref.repo, ref.number)
        meta = PRMeta(
            owner=ref.owner,
            repo=ref.repo,
            number=ref.number,
            title=pr.get("title", ""),
            body=pr.get("body") or "",
            author=(pr.get("user") or {}).get("login", ""),
            base=(pr.get("base") or {}).get("ref", ""),
            head=(pr.get("head") or {}).get("ref", ""),
            head_sha=(pr.get("head") or {}).get("sha", ""),
            labels=[lb.get("name", "") for lb in pr.get("labels", [])],
            changed_files=pr.get("changed_files", 0),
            additions=pr.get("additions", 0),
            deletions=pr.get("deletions", 0),
            url=pr.get("html_url", ""),
        )

        diff = c.get_pr_diff(ref.owner, ref.repo, ref.number)
        diff, diff_truncated = head_tail(
            diff, self.max_diff_bytes // 2, self.max_diff_bytes // 2
        )

        files = self._build_files(ref, meta)
        commits = self._build_commits(ref)
        issues = self._build_issues(ref, meta, commits)
        comments = self._build_comments(ref)

        return ReviewContext(
            meta=meta,
            diff=diff,
            diff_truncated=diff_truncated,
            files=files,
            issues=issues,
            comments=comments,
            commit_messages=commits,
        )

    def _build_files(self, ref: PRRef, meta: PRMeta) -> list[FileContext]:
        raw_files = self.client.get_pr_files(ref.owner, ref.repo, ref.number)
        out: list[FileContext] = []
        head_ref = meta.head_sha or meta.head
        for f in raw_files[: self.max_files]:
            path = f.get("filename", "")
            status = f.get("status", "modified")
            content = ""
            truncated = False
            if status != "removed" and head_ref:
                content = self.client.get_file_content(
                    ref.owner, ref.repo, path, head_ref
                ) or ""
                if content:
                    content, truncated = truncate_bytes(content, self.max_file_bytes)
            out.append(
                FileContext(
                    path=path,
                    status=status,
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    content=content,
                    truncated=truncated,
                )
            )
        return out

    def _build_commits(self, ref: PRRef) -> list[str]:
        commits = self.client.get_pr_commits(ref.owner, ref.repo, ref.number)
        msgs = []
        for cm in commits[: self.max_commits]:
            msg = (cm.get("commit") or {}).get("message", "")
            if msg:
                msgs.append(msg.splitlines()[0])
        return msgs

    def _build_issues(
        self, ref: PRRef, meta: PRMeta, commits: list[str]
    ) -> list[IssueContext]:
        candidates = extract_issue_refs(
            f"{meta.title}\n{meta.body}\n" + "\n".join(commits)
        )
        issues: list[IssueContext] = []
        for num in candidates[: self.max_issues]:
            if num == meta.number:
                continue  # self-reference to the PR itself
            data = self.client.get_issue(ref.owner, ref.repo, num)
            if not data or "pull_request" in data:
                continue  # missing or actually a PR link
            body, truncated = truncate_bytes(
                data.get("body") or "", self.max_issue_bytes
            )
            issues.append(
                IssueContext(
                    number=num,
                    title=data.get("title", ""),
                    body=body,
                    state=data.get("state", ""),
                    url=data.get("html_url", ""),
                    truncated=truncated,
                )
            )
        return issues

    def _build_comments(self, ref: PRRef) -> list[CommentContext]:
        out: list[CommentContext] = []
        try:
            reviews = self.client.get_reviews(ref.owner, ref.repo, ref.number)
            for r in reviews:
                body = (r.get("body") or "").strip()
                if body:
                    out.append(
                        CommentContext(
                            author=(r.get("user") or {}).get("login", ""),
                            body=body,
                            kind="review",
                            created_at=r.get("submitted_at", ""),
                        )
                    )
        except GitHubError:
            pass
        try:
            for rc in self.client.get_review_comments(ref.owner, ref.repo, ref.number):
                out.append(
                    CommentContext(
                        author=(rc.get("user") or {}).get("login", ""),
                        body=rc.get("body") or "",
                        kind="review_comment",
                        path=rc.get("path"),
                        line=rc.get("line") or rc.get("original_line"),
                        created_at=rc.get("created_at", ""),
                    )
                )
        except GitHubError:
            pass
        try:
            for ic in self.client.get_issue_comments(ref.owner, ref.repo, ref.number):
                out.append(
                    CommentContext(
                        author=(ic.get("user") or {}).get("login", ""),
                        body=ic.get("body") or "",
                        kind="issue_comment",
                        created_at=ic.get("created_at", ""),
                    )
                )
        except GitHubError:
            pass
        out = out[: self.max_comments]
        for cm in out:
            cm.body, _ = truncate_bytes(cm.body, self.max_comment_bytes)
        return out
