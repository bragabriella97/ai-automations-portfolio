"""Shared helper: one structured call to Claude, validated against a Pydantic model."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
DRY_RUN = os.getenv("DRY_RUN") == "1" or not os.getenv("ANTHROPIC_API_KEY")

T = TypeVar("T", bound=BaseModel)
_client: anthropic.Anthropic | None = None


def ask(system: str, content: str | list, schema: type[T]) -> T:
    """Send one request and return the parsed, schema-validated answer."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()

    response = _client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Answer was cut off, raise max_tokens")
    out = response.parsed_output
    if out is None:
        raise RuntimeError("No structured answer returned")
    return out


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path}")
