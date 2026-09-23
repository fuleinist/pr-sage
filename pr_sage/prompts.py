"""Prompt construction: system contract + user context assembly (SPEC FR-4/FR-6)."""

from __future__ import annotations

import json

from .models import ReviewContext

SYSTEM_PROMPT = """\
You are PR-Sage, a senior software engineer performing a pull request review.

Rules you must follow:
1. Critique the code, never the person. Acknowledge the effort that went in.
2. Read the FULL FILE CONTENT and related issues, not just the diff — judge
   whether the change fits the codebase's conventions and the issue's intent.
3. Every concern must come with a concrete, actionable suggested change.
4. Severity discipline: "blocking" = must fix before merge (bugs, security,
   data loss); "should-fix" = real problem, fixable in this PR; "nit" = taste
   or minor polish. At most 3 nits total.
5. Do not invent problems to seem thorough. An honest "looks good" beats
   manufactured concerns.
6. Be empathetic in tone: assume good intent, phrase feedback as a colleague
   who wants the author to succeed.

You must reply with STRICT JSON only (no markdown fences, no prose) matching:
{
  "summary": "<2-4 sentence overall assessment>",
  "strengths": ["<what the PR does well>"],
  "concerns": [
    {"severity": "blocking|should-fix|nit", "message": "<issue + why>",
     "file": "<path or omit>", "line": <int or omit>}
  ],
  "suggestions": [
    {"file": "<path>", "line": <int or omit>, "body": "<concrete change>"}
  ],
  "verdict": "approve|request-changes|comment"
}
"""


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body}\n"


def build_user_prompt(ctx: ReviewContext) -> str:
    """Render the assembled ReviewContext into the user prompt."""
    parts: list[str] = []
    m = ctx.meta
    parts.append(
        _section(
            "PULL REQUEST",
            f"Repo: {m.owner}/{m.repo}\nPR #{m.number}: {m.title}\n"
            f"Author: {m.author}  Base: {m.base} <- Head: {m.head}\n"
            f"Labels: {', '.join(m.labels) or '(none)'}\n"
            f"Changed: {m.changed_files} files (+{m.additions}/-{m.deletions})\n\n"
            f"PR description:\n{m.body or '(empty)'}",
        )
    )

    if ctx.commit_messages:
        parts.append(_section("COMMITS", "\n".join(f"- {c}" for c in ctx.commit_messages)))

    if ctx.issues:
        issue_blocks = []
        for iss in ctx.issues:
            issue_blocks.append(
                f"### Issue #{iss.number}: {iss.title} ({iss.state})\n{iss.body or '(empty)'}"
            )
        parts.append(_section("RELATED ISSUES", "\n\n".join(issue_blocks)))

    parts.append(_section("DIFF", ctx.diff or "(empty)"))

    if ctx.files:
        file_blocks = []
        for f in ctx.files:
            header = f"### {f.path} ({f.status}, +{f.additions}/-{f.deletions})"
            body = f.content if f.content else "(content unavailable)"
            file_blocks.append(f"{header}\n```\n{body}\n```")
        parts.append(_section("FULL FILE CONTENTS (head version)", "\n\n".join(file_blocks)))

    if ctx.comments:
        comment_blocks = []
        for cm in ctx.comments:
            loc = f" on {cm.path}:{cm.line}" if cm.path else ""
            comment_blocks.append(f"- [{cm.kind}] {cm.author}{loc}: {cm.body}")
        parts.append(
            _section(
                "PRIOR REVIEW HISTORY",
                "\n".join(comment_blocks)
                + "\n\nDo not repeat feedback already given above unless it is unresolved.",
            )
        )

    parts.append("Now produce your strict-JSON review of this pull request.")
    return "\n".join(parts)


def repair_prompt(raw: str) -> str:
    """One-shot repair request when the model's reply is not valid JSON."""
    return (
        "Your previous reply was not valid JSON. Extract the review into the exact "
        "JSON schema from the system prompt. Reply with JSON only.\n\nPrevious reply:\n"
        + raw[:8000]
    )


def as_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
