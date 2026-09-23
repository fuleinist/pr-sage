"""Thin GitHub REST client using only the stdlib (urllib).

All network access lives here so the rest of the package is trivially
mockable. Token comes from GITHUB_TOKEN / GH_TOKEN env vars.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
USER_AGENT = "pr-sage/0.1.0"


class GitHubError(RuntimeError):
    """Raised on any non-2xx GitHub API response or transport failure."""


class GitHubClient:
    def __init__(self, token: str | None = None, api_root: str = API_ROOT):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        self.api_root = api_root.rstrip("/")

    def _request(self, path: str, *, accept: str = "application/vnd.github+json",
                 method: str = "GET", payload: dict | None = None) -> tuple[int, str]:
        url = path if path.startswith("http") else f"{self.api_root}{path}"
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubError(f"GitHub API {exc.code} for {url}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"GitHub API unreachable ({url}): {exc.reason}") from exc

    def _json(self, path: str, **kw) -> object:
        _, body = self._request(path, **kw)
        return json.loads(body)

    # --- PR data -------------------------------------------------------

    def get_pr(self, owner: str, repo: str, number: int) -> dict:
        return self._json(f"/repos/{owner}/{repo}/pulls/{number}")  # type: ignore[return-value]

    def get_pr_diff(self, owner: str, repo: str, number: int) -> str:
        _, body = self._request(f"/repos/{owner}/{repo}/pulls/{number}",
                                accept="application/vnd.github.diff")
        return body

    def get_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        return self._json(f"/repos/{owner}/{repo}/pulls/{number}/files?per_page=100")  # type: ignore[return-value]

    def get_pr_commits(self, owner: str, repo: str, number: int) -> list[dict]:
        return self._json(f"/repos/{owner}/{repo}/pulls/{number}/commits?per_page=100")  # type: ignore[return-value]

    def get_issue_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        return self._json(f"/repos/{owner}/{repo}/issues/{number}/comments?per_page=100")  # type: ignore[return-value]

    def get_review_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        return self._json(f"/repos/{owner}/{repo}/pulls/{number}/comments?per_page=100")  # type: ignore[return-value]

    def get_reviews(self, owner: str, repo: str, number: int) -> list[dict]:
        return self._json(f"/repos/{owner}/{repo}/pulls/{number}/reviews?per_page=100")  # type: ignore[return-value]

    def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        """Raw file content at *ref*; None when missing (e.g. deleted files)."""
        import base64
        try:
            data = self._json(f"/repos/{owner}/{repo}/contents/{urllib.request.quote(path)}?ref={urllib.request.quote(ref, safe='')}")
        except GitHubError:
            return None
        if not isinstance(data, dict) or "content" not in data:
            return None
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None

    def get_issue(self, owner: str, repo: str, number: int) -> dict | None:
        try:
            data = self._json(f"/repos/{owner}/{repo}/issues/{number}")
        except GitHubError:
            return None
        return data if isinstance(data, dict) else None

    # --- writes ----------------------------------------------------------

    def post_review(self, owner: str, repo: str, number: int, body: str,
                    event: str = "COMMENT") -> dict:
        payload = {"body": body, "event": event}
        return self._json(  # type: ignore[return-value]
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            method="POST", payload=payload,
        )


def build_review_body_markdown(review) -> str:
    """Render a Review model into the markdown body for a GitHub review.

    Kept here (not in review.py) so posting is a self-contained payload
    builder that is easy to unit-test.
    """
    lines = ["## 🧙 PR-Sage review", "", review.summary, ""]
    if review.strengths:
        lines.append("### Strengths")
        lines += [f"- {s}" for s in review.strengths]
        lines.append("")
    if review.concerns:
        icon = {"blocking": "🔴", "should-fix": "🟡", "nit": "🔵"}
        lines.append("### Concerns")
        for c in review.concerns:
            loc = f" — `{c.file}" + (f":{c.line}`" if c.line else "`") if c.file else ""
            lines.append(f"- {icon.get(c.severity, '⚪')} **{c.severity}**{loc}: {c.message}")
        lines.append("")
    if review.suggestions:
        lines.append("### Suggestions")
        for s in review.suggestions:
            loc = f"`{s.file}" + (f":{s.line}`" if s.line else "`")
            lines.append(f"- {loc}: {s.body}")
        lines.append("")
    if review.verdict:
        lines.append(f"**Verdict:** {review.verdict}")
    lines += ["", "<sub>Generated by [PR-Sage](https://github.com/fuleinist/pr-sage) — AI review, verify before acting.</sub>"]
    return "\n".join(lines)
