"""CLI entry point: pr-sage review <owner/repo#N> [options] (SPEC FR-1/FR-5)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import __version__
from .context import ContextBuilder, RefParseError, parse_pr_ref
from .github_client import GitHubClient, GitHubError, build_review_body_markdown
from .llm import LLMError, get_provider
from .prompts import SYSTEM_PROMPT, build_user_prompt, repair_prompt
from .review import parse_review, render_markdown

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LLM = 3
EXIT_GITHUB = 4


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-sage",
        description="AI-powered PR reviewer with full-file context, related issues, and review history.",
    )
    p.add_argument("--version", action="version", version=f"pr-sage {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("review", help="review a pull request")
    r.add_argument(
        "ref",
        nargs="?",
        help="PR reference: owner/repo#123, owner/repo/pull/123, or a PR URL",
    )
    r.add_argument("--repo", help="owner/repo (alternative to the positional ref)")
    r.add_argument("--pr", type=int, help="PR number (with --repo)")
    r.add_argument(
        "--provider",
        choices=["ollama", "openai", "echo"],
        default="ollama",
        help="LLM backend (env: PR_SAGE_PROVIDER; default: ollama)",
    )
    r.add_argument("--model", help="model name override (env: PR_SAGE_MODEL)")
    r.add_argument("--json", action="store_true", help="emit parsed review as JSON")
    r.add_argument(
        "--post",
        action="store_true",
        help="post the review back to GitHub as a COMMENT review",
    )
    r.add_argument(
        "--dry-run",
        action="store_true",
        help="build context and show prompt stats without calling the LLM",
    )
    return p


def _resolve_ref(args: argparse.Namespace):
    if args.ref:
        return parse_pr_ref(args.ref)
    if args.repo and args.pr:
        if "/" not in args.repo:
            raise RefParseError("--repo must be in owner/repo form")
        owner, repo = args.repo.split("/", 1)
        from .context import PRRef

        return PRRef(owner=owner, repo=repo, number=args.pr)
    raise RefParseError("provide a PR reference positionally, or both --repo and --pr")


def cmd_review(args: argparse.Namespace) -> int:
    try:
        ref = _resolve_ref(args)
    except RefParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    provider_name = args.provider
    client = GitHubClient()
    if provider_name != "echo" and not client.token:
        print(
            "warning: no GITHUB_TOKEN set; unauthenticated API calls are heavily rate-limited",
            file=sys.stderr,
        )

    try:
        ctx = ContextBuilder(client).build(ref)
    except GitHubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_GITHUB

    label = f"{ref.owner}/{ref.repo}#{ref.number} — {ctx.meta.title}"
    system, user = SYSTEM_PROMPT, build_user_prompt(ctx)

    if args.dry_run:
        print(f"PR: {label}")
        print(f"context: {len(ctx.files)} files, {len(ctx.issues)} issues, "
              f"{len(ctx.comments)} prior comments, diff_truncated={ctx.diff_truncated}")
        print(f"prompt size: system={len(system)} bytes, user={len(user)} bytes")
        return EXIT_OK

    try:
        provider = get_provider(provider_name)
        if args.model:
            provider.model = args.model  # type: ignore[attr-defined]
        raw = provider.complete(system, user)
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LLM

    review = parse_review(raw)
    if not review.structured:
        try:
            repaired = provider.complete(system, repair_prompt(raw))  # type: ignore[union-attr]
            review = parse_review(raw, repaired)
        except LLMError:
            pass  # keep the unstructured fallback

    if args.json:
        data = asdict(review)
        data.pop("raw", None)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(review, label))

    if args.post:
        body = build_review_body_markdown(review)
        try:
            client.post_review(ref.owner, ref.repo, ref.number, body, event="COMMENT")
        except GitHubError as exc:
            print(f"error posting review: {exc}", file=sys.stderr)
            return EXIT_GITHUB
        print(f"\nReview posted to {ctx.meta.url or label}")

    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review":
        return cmd_review(args)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
