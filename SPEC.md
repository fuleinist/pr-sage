# PR-Sage — Specification

## Vision

An AI-powered PR reviewer that goes beyond diff-scanning. It reads the **full
file context** of changed files, discovers **related issues**, and consults
**previous review history** before producing **actionable, empathetic**
feedback a human maintainer would be proud to post.

## Goals (v1)

1. CLI tool `pr-sage` that reviews a GitHub pull request from the terminal.
2. Deep context assembly: PR metadata + diff + full contents of changed files
   (head version) + linked/referenced issues + prior review comments.
3. LLM backends: local **Ollama** (default), **OpenAI-compatible** endpoints,
   and a dry-run **echo** provider for tests/offline use.
4. Structured review output: overall summary, strengths, concerns with
   severity, per-file suggestions with line anchors, and an empathetic tone.
5. Optional `--post` to publish the review back to GitHub (COMMENT event).
6. Deterministic, mockable core: network calls isolated behind small clients,
   unit-tested without hitting GitHub or any LLM.

## Non-goals (v1)

- GitHub App / webhook-driven automation (CLI-first; CI usage documented).
- Automatic APPROVE/REQUEST_CHANGES events (only COMMENT).
- Cross-repo context, org policy rules, custom rule files.
- GUI/web dashboard.

## Architecture

```
pr_sage/
  cli.py          argparse entry point: pr-sage review <owner/repo#N> [opts]
  github_client.py  thin GitHub REST client (urllib; GITHUB_TOKEN)
  context.py      ContextBuilder: assembles ReviewContext from GH data
  llm.py          Provider protocol + Ollama/OpenAI/Echo implementations
  prompts.py      system+user prompt construction, output contract
  review.py       parses LLM JSON into Review model; renders markdown
  models.py       dataclasses: ReviewContext, FileContext, Review, ...
  truncation.py   token-budget-aware trimming helpers
```

## Functional Requirements

### FR-1 PR reference parsing
- Accept `owner/repo#123`, `owner/repo/pull/123`, full PR URLs, or
  `--repo owner/repo --pr 123`. Invalid input → clear error, exit 2.

### FR-2 Context assembly
- Fetch PR metadata (title, body, author, base/head, labels, changed counts).
- Fetch the diff (`Accept: application/vnd.github.diff`).
- Fetch full head-version contents of each changed file (cap: 12 files,
  24 KB each by default; configurable).
- Extract issue references from PR title/body/commits (`#123`,
  `fixes #123`, full issue URLs) and fetch up to 5 issue bodies.
- Fetch prior review comments + issue comments on the PR (up to 20).
- Every context section carries a byte budget; overflow trims with an
  explicit `... [truncated N bytes] ...` marker.

### FR-3 LLM providers
- `ollama` (default): POST `http://host:11434/api/chat`, model configurable
  (`PR_SAGE_MODEL`, default `qwen2.5-coder:7b`).
- `openai`: POST `{base_url}/chat/completions` with `Authorization: Bearer`.
- `echo`: returns a fixed valid review JSON (tests, offline demos).
- Provider errors → single retry, then clean failure message, exit 3.

### FR-4 Review generation contract
- Prompt instructs the model to return **strict JSON** matching:
  `{summary, strengths[], concerns[{severity, message, file?, line?}],
  suggestions[{file, line?, body}], verdict}`.
- Parser tolerates code fences and leading prose; malformed JSON after
  one repair attempt → raw text fallback rendered under "Unstructured review".

### FR-5 Rendering & posting
- Terminal output: markdown-ish review with severity emoji, grouped by file.
- `--post`: publish as a single PR review (event=COMMENT) via
  `POST /repos/{o}/{r}/pulls/{n}/reviews`; requires token with repo scope.
- `--json`: emit the parsed review as JSON instead of rendering.

### FR-6 Empathy & actionability (prompt-level requirements)
- System prompt enforces: critique code not people, acknowledge effort,
  every concern paired with a concrete suggested change, severity discipline
  (blocking / should-fix / nit), no nitpicking storms (≤3 nits).

## Acceptance Criteria

- [ ] `pr-sage review octocat/hello-world#1 --provider echo` produces a
      structured review offline.
- [ ] Reference parsing handles all four input forms (unit-tested).
- [ ] ContextBuilder respects every cap and emits truncation markers
      (unit-tested with fake GitHub data).
- [ ] Issue-reference extraction finds `#N`, `fixes #N`, and URL forms.
- [ ] Review JSON parser recovers from fenced/prose-wrapped payloads.
- [ ] Ollama and OpenAI providers build correct request payloads
      (unit-tested against a local stub server or mocked urlopen).
- [ ] `--post` path constructs the correct GitHub review payload.
- [ ] Full test suite passes offline: `python -m pytest` green on a machine
      with no GITHUB_TOKEN and no Ollama running.
- [ ] README documents install, usage, env vars, and CI example.

## Budget

Max 10 spec→build→verify cycles. Commit after each cycle. Kill criteria per
agent skill: pause if no working prototype by cycle 10.
