# 🧙 PR-Sage

An AI-powered PR reviewer that doesn't just scan diffs — it reads the **full
file context**, **related issues**, and **previous review history** to give
actionable, empathetic feedback.

Most review tools do surface-level linting. PR-Sage assembles the same context
a thoughtful human maintainer would gather before reviewing, then asks a local
(or hosted) LLM to produce a structured, severity-disciplined review.

## Features

- **Deep context assembly** — PR metadata, diff, full head-version file
  contents, linked issues (extracted from `fixes #N`, `closes #N`, URLs),
  commit messages, and prior reviews/comments, all within configurable byte
  budgets with explicit truncation markers.
- **Local-first** — defaults to [Ollama](https://ollama.com); also supports any
  OpenAI-compatible endpoint. An `echo` provider runs fully offline.
- **Structured output** — strict-JSON review contract: summary, strengths,
  concerns with severity (`blocking` / `should-fix` / `nit`), per-file
  suggestions with line anchors, and a verdict. Malformed output triggers one
  repair attempt, then a readable unstructured fallback.
- **Empathetic by design** — the system prompt enforces: critique code not
  people, pair every concern with a concrete fix, at most 3 nits, honest
  "looks good" over manufactured concerns.
- **Post back to GitHub** — `--post` publishes the review as a COMMENT-event
  PR review.
- **Zero dependencies** — stdlib only (Python ≥ 3.10).

## Install

```bash
git clone https://github.com/fuleinist/pr-sage
cd pr-sage
pip install -e .          # or: pipx install .
```

## Usage

```bash
export GITHUB_TOKEN=ghp_xxx        # recommended; unauthenticated is rate-limited

# review a PR (defaults to local Ollama)
pr-sage review owner/repo#123

# all reference forms work
pr-sage review owner/repo/pull/123
pr-sage review https://github.com/owner/repo/pull/123
pr-sage review --repo owner/repo --pr 123

# inspect what context would be sent, without calling the LLM
pr-sage review owner/repo#123 --dry-run

# structured JSON output (scripting)
pr-sage review owner/repo#123 --json

# post the review back to GitHub
pr-sage review owner/repo#123 --post

# fully offline demo (no GitHub token needed for echo? — context still fetches;
# use a public repo)
pr-sage review octocat/hello-world#1 --provider echo
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` / `GH_TOKEN` | — | GitHub API auth (needs `repo` scope to `--post`) |
| `PR_SAGE_MODEL` | `qwen2.5-coder:7b` | Ollama model name |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OPENAI_API_KEY` | — | Key for the `openai` provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `PR_SAGE_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI provider model |

### CI example

```yaml
- name: PR-Sage review
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    pipx install git+https://github.com/fuleinist/pr-sage
    pr-sage review "${{ github.repository }}#${{ github.event.pull_request.number }}" \
      --provider openai --post
```

## Example output

```
== PR-Sage review — octo/demo#5 — Fix cache invalidation bug ==

Solid PR with one blocking issue.

Strengths:
  + Clear naming
  + Good test coverage

Concerns:
  [BLOCKING] (db.py:42) SQL injection in query builder
  [nit] Trailing whitespace

Suggestions:
  * db.py:42 — Use parameterized queries

Verdict: REQUEST CHANGES
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest        # 46 tests, fully offline (no token, no Ollama)
```

## Architecture

See [SPEC.md](SPEC.md) for the full specification and acceptance criteria.

```
pr_sage/
  cli.py            argparse entry: pr-sage review <ref> [opts]
  github_client.py  thin GitHub REST client (stdlib urllib)
  context.py        ContextBuilder: budgets, truncation, issue-ref extraction
  llm.py            Ollama / OpenAI-compatible / Echo providers
  prompts.py        system contract + user prompt assembly
  review.py         JSON recovery, Review model parsing, markdown rendering
  models.py         dataclasses
  truncation.py     byte-budget trimming helpers
```

## Limitations (v1)

- CLI-only; no webhook/GitHub App automation yet.
- Only posts `COMMENT` reviews (never auto-approves).
- Context caps (12 files × 24 KB, 48 KB diff) suit small/medium PRs; huge PRs
  get trimmed with markers.

## License

MIT — see [LICENSE](LICENSE).
