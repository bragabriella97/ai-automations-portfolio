"""Inbox Zero Agent: triage every email and draft replies for the ones that need a person."""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

OWNER = "Ana"  # the inbox owner the replies are signed by

SYSTEM = f"""You are the executive assistant of {OWNER}, who runs a small coaching business.
Triage one email at a time.
- reply_needed: a real person is waiting for an answer from {OWNER}.
- action_needed: no reply, but {OWNER} must do something (pay, update, check).
- fyi: useful to know, nothing to do.
- newsletter: marketing or automated digests.
- spam: scams, phishing, unsolicited prizes. Never draft replies to spam.
For reply_needed, write a short, warm and direct reply signed "{OWNER}".
Never confirm dates, prices or payments you cannot see: say you will check, or offer options.
Leave draft_reply empty for every other category."""


class Triage(BaseModel):
    category: Literal["reply_needed", "action_needed", "fyi", "newsletter", "spam"]
    priority: Literal["high", "medium", "low"]
    summary: str
    next_step: str
    draft_reply: str


def main() -> None:
    emails = json.loads((HERE / "data" / "emails.json").read_text(encoding="utf-8"))
    if DRY_RUN:
        print(f"DRY RUN: {len(emails)} emails loaded, no API key, nothing sent.")
        return

    results = []
    for e in emails:
        print(f"- {e['subject']}")
        t = ask(SYSTEM, f"From: {e['from']}\nSubject: {e['subject']}\n\n{e['body']}", Triage)
        results.append({**e, **t.model_dump()})

    order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: order[r["priority"]])

    lines = [
        "# Inbox triage",
        "",
        f"_Last run: {run_stamp()} · {len(results)} emails · sample inbox, fictional data_",
        "",
        "| Priority | Category | From | Subject | Next step |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['priority']} | {r['category']} | {r['from']} | {r['subject']} | {r['next_step']} |")

    lines += ["", "## Reply drafts (waiting for approval)", ""]
    for r in results:
        if r["draft_reply"]:
            lines += [f"### Re: {r['subject']}", f"To: {r['from']}", "", r["draft_reply"], ""]

    out = HERE / "output"
    write(out / "triage.md", "\n".join(lines))
    write(out / "triage.json", json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
