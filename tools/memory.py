"""Jarvis ki yaaddasht: user ke baare mein baatein memory.json mein save hoti hain."""

import json
from pathlib import Path

from anthropic import beta_tool

MEMORY_FILE = Path(__file__).resolve().parent.parent / "memory.json"


def _load() -> list[str]:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return []


@beta_tool
def remember(fact: str) -> str:
    """Save a fact about the user to long-term memory (name, goals, preferences, etc).

    Args:
        fact: One short fact, e.g. "User's favourite language is Python".
    """
    facts = _load()
    if fact not in facts:
        facts.append(fact)
        MEMORY_FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    return "Saved to memory."


@beta_tool
def recall() -> str:
    """Read everything saved in long-term memory about the user."""
    facts = _load()
    return "\n".join(f"- {f}" for f in facts) if facts else "Memory is empty."
