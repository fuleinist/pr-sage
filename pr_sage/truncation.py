"""Byte-budget-aware truncation helpers.

All budgets are in bytes (approximating tokens well enough for prompt
assembly). Trimming always leaves an explicit marker so the LLM knows
content was cut.
"""

from __future__ import annotations


def truncate_bytes(text: str, budget: int) -> tuple[str, bool]:
    """Trim *text* to at most *budget* bytes.

    Returns (trimmed_text, was_truncated). Keeps the HEAD of the text —
    for source files the top (imports, signatures) is most informative.
    """
    if budget <= 0:
        return "", bool(text)
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= budget:
        return text, False
    # Cut on a UTF-8 boundary.
    cut = encoded[:budget]
    trimmed = cut.decode("utf-8", errors="ignore")
    removed = len(encoded) - len(trimmed.encode("utf-8"))
    marker = f"\n... [truncated {removed} bytes] ...\n"
    return trimmed + marker, True


def head_tail(text: str, head_budget: int, tail_budget: int) -> tuple[str, bool]:
    """Keep the head and tail of *text*, dropping the middle when oversized.

    Useful for diffs where both the start (context) and the end matter.
    """
    encoded = text.encode("utf-8", errors="replace")
    total = head_budget + tail_budget
    if len(encoded) <= total:
        return text, False
    head = encoded[:head_budget].decode("utf-8", errors="ignore")
    tail = encoded[-tail_budget:].decode("utf-8", errors="ignore")
    removed = len(encoded) - len(head.encode()) - len(tail.encode())
    return f"{head}\n... [truncated {removed} bytes] ...\n{tail}", True
