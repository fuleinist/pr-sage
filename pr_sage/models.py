"""Core data models for PR-Sage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileContext:
    """Full head-version content of one changed file."""

    path: str
    status: str  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    content: str = ""
    truncated: bool = False


@dataclass
class IssueContext:
    """A related issue referenced by the PR."""

    number: int
    title: str
    body: str = ""
    state: str = "open"
    url: str = ""
    truncated: bool = False


@dataclass
class CommentContext:
    """A prior review/issue comment on the PR."""

    author: str
    body: str
    kind: str = "issue_comment"  # issue_comment | review_comment | review
    path: str | None = None
    line: int | None = None
    created_at: str = ""


@dataclass
class PRMeta:
    """PR metadata."""

    owner: str
    repo: str
    number: int
    title: str
    body: str = ""
    author: str = ""
    base: str = ""
    head: str = ""
    labels: list[str] = field(default_factory=list)
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    url: str = ""


@dataclass
class ReviewContext:
    """Everything assembled for the LLM."""

    meta: PRMeta
    diff: str = ""
    diff_truncated: bool = False
    files: list[FileContext] = field(default_factory=list)
    issues: list[IssueContext] = field(default_factory=list)
    comments: list[CommentContext] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)


@dataclass
class Concern:
    severity: str  # blocking | should-fix | nit
    message: str
    file: str | None = None
    line: int | None = None


@dataclass
class Suggestion:
    file: str
    body: str
    line: int | None = None


@dataclass
class Review:
    """Parsed structured review from the LLM."""

    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    concerns: list[Concern] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    verdict: str = ""  # approve | request-changes | comment
    raw: str = ""
    structured: bool = True
