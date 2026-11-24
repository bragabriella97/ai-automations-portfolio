"""LinkedIn Outreach Engine: a 30 day, multi-touch campaign that stops itself on a no and alerts you on a yes.

For each lead, Claude writes the whole sequence once, grounded in her profile and latest post.
Code decides when each touch is due, which channel it uses, and when the campaign must stop.
Every reply is read by Claude and sorted: interested (hot lead alert), not interested (stop and never
contact again), question (pause and draft an answer for approval) or out of office (keep going).

Nothing is sent and nothing is clicked on LinkedIn: automating LinkedIn breaks its rules.
The engine produces a task queue and drafts that a person (or an approved tool) executes.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

SENDER = "Gabriella"
NOTE_LIMIT = 300  # LinkedIn connection note limit, in characters
TODAY = date.fromisoformat(os.getenv("TODAY") or date.today().isoformat())
OUT = HERE / "output"
STATE_FILE = OUT / "state.json"

# (day, step, channel). "linkedin*" means LinkedIn if connected, otherwise email.
STEPS = [
    (0, "profile_view", "linkedin"),
    (1, "connection_request", "linkedin"),
    (3, "message", "linkedin"),
    (7, "email", "email"),
    (14, "follow_up_1", "linkedin*"),
    (21, "follow_up_2", "email"),
    (30, "breakup", "email"),
]

SEQUENCE_SYSTEM = f"""You write outreach for {SENDER}, an automation consultant for women who run small businesses.
Write one 30 day sequence for one lead. Every touch must mention something specific from her post or her business,
and each touch must add something new (an idea, a small example, a question), never "just checking in".
Tone: warm, peer to peer, short. No hype, no flattery, no fake familiarity. Never invent facts about her.
connection_note: under 280 characters. Messages: under 600 characters. Emails: under 120 words.
breakup: a kind last email that closes the loop and leaves the door open.
Sign messages and emails "{SENDER}"."""

REPLY_SYSTEM = f"""You read a reply to {SENDER}'s outreach and sort it.
positive: she wants to talk, book a call or know prices. negative: no, not now, stop, unsubscribe.
question: she asks something but has not said yes or no. out_of_office: automatic away message.
other: anything else. For question, write a short, honest suggested_reply that answers it and offers a call.
For every other intent, leave suggested_reply empty. Never promise prices or results."""


class Sequence(BaseModel):
    connection_note: str
    message: str
    email_subject: str
    email_body: str
    follow_up_1: str
    follow_up_2_subject: str
    follow_up_2_body: str
    breakup_subject: str
    breakup_body: str


class Reply(BaseModel):
    intent: Literal["positive", "negative", "question", "out_of_office", "other"]
    summary: str
    suggested_reply: str


def d(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def lead_context(lead: dict) -> str:
    return (
        f"Lead: {lead['name']}, {lead['title']} at {lead['company']}\n"
        f"About the business: {lead['about']}\nHer latest post: \"{lead['recent_post']}\""
    )


def copy_for(step: str, seq: Sequence) -> str:
    return {
        "profile_view": "",
        "connection_request": seq.connection_note,
        "message": seq.message,
        "email": f"Subject: {seq.email_subject}\n\n{seq.email_body}",
        "follow_up_1": seq.follow_up_1,
        "follow_up_2": f"Subject: {seq.follow_up_2_subject}\n\n{seq.follow_up_2_body}",
        "breakup": f"Subject: {seq.breakup_subject}\n\n{seq.breakup_body}",
    }[step]


def simulate(lead: dict, seq: Sequence, replies: dict) -> dict:
    """Walk the campaign day by day, from the start date to today, and apply the stop rules."""
    start, connected = d(lead["started_on"]), d(lead["connected_on"])
    events, status, alert = [], "active", None
    by_day = {d(r["on"]): r for r in lead["replies"]}
    day = start
    while day <= TODAY and status == "active":
        for offset, step, channel in STEPS:
            if start + timedelta(days=offset) != day:
                continue
            if channel.startswith("linkedin") and step not in ("profile_view", "connection_request"):
                if not connected or connected > day:
                    if channel == "linkedin":
                        events.append((day, step, "skipped", "Not connected yet, the day 7 email covers it."))
                        continue
                    channel = "email"
            text = copy_for(step, seq)
            flag = ""
            if step == "connection_request" and len(text) > NOTE_LIMIT:
                flag = f" (too long: {len(text)} characters, edit before sending)"
            done = "done" if day < TODAY else "due today"
            events.append((day, step, f"{done} · {channel.rstrip('*')}{flag}", text))
        if day == connected:
            events.append((day, "connected", "accepted", ""))
        if day in by_day:
            r, c = by_day[day], replies[by_day[day]["on"]]
            events.append((day, "reply", f"{r['channel']} · {c['intent']}", f"\"{r['text']}\"\n\n{c['summary']}"))
            if c["intent"] == "positive":
                status, alert = "hot lead", c["summary"]
            elif c["intent"] == "negative":
                status = "not interested"
            elif c["intent"] in ("question", "other"):
                status = "conversation"
        day += timedelta(days=1)
    if status == "active" and TODAY >= start + timedelta(days=STEPS[-1][0]):
        status = "finished, no reply"
    nxt = ""
    if status == "active":
        upcoming = [start + timedelta(days=o) for o, _, _ in STEPS if start + timedelta(days=o) > TODAY]
        nxt = upcoming[0].isoformat() if upcoming else ""
    return {"events": events, "status": status, "alert": alert, "next": nxt}


def main() -> None:
    leads = json.loads((HERE / "data" / "leads.json").read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    print(f"Today: {TODAY.isoformat()} · {len(leads)} leads")

    for lead in leads:
        st = state.setdefault(lead["id"], {"replies": {}})
        new_replies = [r for r in lead["replies"] if r["on"] not in st["replies"] and d(r["on"]) <= TODAY]
        todo = (["sequence"] if "sequence" not in st else []) + [f"reply {r['on']}" for r in new_replies]
        print(f"- {lead['name']}: {', '.join(todo) or 'nothing new for Claude'}")
        if DRY_RUN:
            continue
        if "sequence" not in st:
            st["sequence"] = ask(SEQUENCE_SYSTEM, lead_context(lead), Sequence).model_dump()
        for r in new_replies:
            c = ask(REPLY_SYSTEM, f"{lead_context(lead)}\n\nHer reply ({r['channel']}): \"{r['text']}\"", Reply)
            st["replies"][r["on"]] = c.model_dump()

    if DRY_RUN:
        print("DRY RUN: no API key, nothing written.")
        return

    board = [
        "# LinkedIn campaign",
        "",
        f"_Last run: {run_stamp()} · today is {TODAY.isoformat()} · fictional leads · nothing is sent automatically_",
        "",
        "| Lead | Company | Status | Touches | Next touch |",
        "|---|---|---|---|---|",
    ]
    alerts, dnc, due_today = [], [], []
    for lead in leads:
        st = state[lead["id"]]
        res = simulate(lead, Sequence(**st["sequence"]), st["replies"])
        touches = sum(1 for e in res["events"] if e[2].startswith(("done", "due")))
        board.append(
            f"| [{lead['name']}](leads/{lead['id']}.md) | {lead['company']} | **{res['status']}** | {touches} | {res['next'] or '-'} |"
        )
        timeline = [f"# {lead['name']} · {lead['company']}", "", f"**Status:** {res['status']}", ""]
        for day, step, what, text in res["events"]:
            timeline.append(f"### {day.isoformat()} · {step.replace('_', ' ')} · {what}")
            if text:
                timeline += ["", text, ""]
            if what.startswith("due today"):
                due_today.append(f"- {lead['name']}: {step.replace('_', ' ')}")
        for on, c in st["replies"].items():
            if c["suggested_reply"]:
                timeline += ["", f"## Suggested answer to her {on} reply (draft, waiting for approval)", "", c["suggested_reply"]]
        write(OUT / "leads" / f"{lead['id']}.md", "\n".join(timeline))
        if res["alert"]:
            alerts.append(f"## 🔥 {lead['name']}, {lead['company']}\n{res['alert']}\n\nStop the sequence and reply yourself: [timeline](leads/{lead['id']}.md)\n")
        if res["status"] == "not interested":
            dnc.append({"name": lead["name"], "email": lead["email"], "since": max(st["replies"])})

    board += ["", "## Due today", *(due_today or ["- Nothing due today."]), "", "Hot leads: [alerts.md](alerts.md)"]
    write(OUT / "campaign.md", "\n".join(board))
    write(OUT / "alerts.md", "\n".join(["# Hot lead alerts", "", *(alerts or ["No hot leads yet."])]))
    write(OUT / "do-not-contact.json", json.dumps(dnc, indent=2, ensure_ascii=False))
    write(STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
