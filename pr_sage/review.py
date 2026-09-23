"""Parse LLM output into a Review and render it for the terminal (SPEC FR-4/FR-5)."""

from __future__ import annotations

import json
import re

from .models import Concern, Review, Suggestion

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_FIRST_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> str:
    """Recover a JSON object from fenced or prose-wrapped model output."""
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        if candidate.startswith("{"):
            return candidate
    m = _FIRST_BRACE_RE.search(text)
    if m:
        return m.group(0)
    return text


def parse_review(raw: str, repaired: str | None = None) -> Review:
    """Parse model output; fall back to *repaired*, then to unstructured."""
    for candidate in (raw, repaired):
        if not candidate:
            continue
        try:
            data = json.loads(extract_json(candidate))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        return Review(
            summary=str(data.get("summary", "")).strip(),
            strengths=[str(s) for s in data.get("strengths", []) if str(s).strip()],
            concerns=[
                Concern(
                    severity=str(c.get("severity", "nit")).lower().strip()
                    if isinstance(c, dict)
                    else "nit",
                    message=str(c.get("message", "")) if isinstance(c, dict) else str(c),
                    file=(c.get("file") if isinstance(c, dict) else None) or None,
                    line=(int(c["line"]) if isinstance(c, dict) and c.get("line") else None),
                )
                for c in data.get("concerns", [])
            ],
            suggestions=[
                Suggestion(
                    file=str(s.get("file", "")),
                    line=(int(s["line"]) if s.get("line") else None),
                    body=str(s.get("body", "")),
                )
                for s in data.get("suggestions", [])
                if isinstance(s, dict)
            ],
            verdict=str(data.get("verdict", "comment")).lower().strip(),
            raw=raw,
            structured=True,
        )
    return Review(summary="", raw=raw, structured=False)


_SEVERITY_ICON = {"blocking": "[BLOCKING]", "should-fix": "[SHOULD-FIX]", "nit": "[nit]"}
_VERDICT_LABEL = {
    "approve": "APPROVE",
    "request-changes": "REQUEST CHANGES",
    "comment": "COMMENT",
}


def render_markdown(review: Review, pr_label: str = "") -> str:
    """Terminal-friendly markdown rendering of a Review."""
    lines: list[str] = []
    header = "PR-Sage review"
    if pr_label:
        header += f" — {pr_label}"
    lines.append(f"== {header} ==")
    lines.append("")

    if not review.structured:
        lines.append("Unstructured review (model did not return valid JSON):")
        lines.append("")
        lines.append(review.raw.strip())
        return "\n".join(lines)

    if review.summary:
        lines.append(review.summary)
        lines.append("")
    if review.strengths:
        lines.append("Strengths:")
        lines += [f"  + {s}" for s in review.strengths]
        lines.append("")
    if review.concerns:
        lines.append("Concerns:")
        for c in review.concerns:
            icon = _SEVERITY_ICON.get(c.severity, f"[{c.severity}]")
            loc = ""
            if c.file:
                loc = f" ({c.file}" + (f":{c.line})" if c.line else ")")
            lines.append(f"  {icon}{loc} {c.message}")
        lines.append("")
    if review.suggestions:
        lines.append("Suggestions:")
        for s in review.suggestions:
            loc = f"{s.file}" + (f":{s.line}" if s.line else "")
            lines.append(f"  * {loc} — {s.body}")
        lines.append("")
    verdict = _VERDICT_LABEL.get(review.verdict, review.verdict.upper())
    lines.append(f"Verdict: {verdict}")
    return "\n".join(lines)
