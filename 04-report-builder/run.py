"""Autonomous Report Builder: messy meeting notes in, a client ready report out, waiting for human approval."""

import sys
from pathlib import Path

from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

SYSTEM = """You turn raw meeting notes from an automation consultant into a clear client report.
Use only what is in the notes. Do not add promises, prices or dates that are not there.
If something was left open, list it under open_questions instead of deciding it.
Write in plain, friendly English the client can read in two minutes."""


class ActionItem(BaseModel):
    task: str
    owner: str
    due: str


class Report(BaseModel):
    client: str
    title: str
    summary: str
    the_problem: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    next_meeting: str


def render(r: Report, source: str) -> str:
    lines = [
        f"# {r.title}",
        "",
        f"> **Status: draft, waiting for approval** · generated {run_stamp()} from `{source}` (fictional notes)",
        "",
        f"**Client:** {r.client}",
        "",
        "## Summary",
        r.summary,
        "",
        "## What we heard",
        *[f"- {p}" for p in r.the_problem],
        "",
        "## Decisions",
        *([f"- {d}" for d in r.decisions] or ["- None yet"]),
        "",
        "## Next steps",
        "| Task | Owner | Due |",
        "|---|---|---|",
        *[f"| {a.task} | {a.owner} | {a.due} |" for a in r.action_items],
        "",
        "## Open questions",
        *([f"- {q}" for q in r.open_questions] or ["- None"]),
        "",
        f"**Next meeting:** {r.next_meeting or 'to be scheduled'}",
    ]
    return "\n".join(lines)


def main() -> None:
    notes = sorted((HERE / "data" / "notes").glob("*.md"))
    if DRY_RUN:
        print(f"DRY RUN: {len(notes)} meeting notes found, no API key, nothing sent.")
        return

    for n in notes:
        print(f"- {n.name}")
        report = ask(SYSTEM, n.read_text(encoding="utf-8"), Report)
        write(HERE / "output" / "pending-approval" / n.name, render(report, n.name))


if __name__ == "__main__":
    main()
