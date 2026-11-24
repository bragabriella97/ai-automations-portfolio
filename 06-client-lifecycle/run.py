"""Client Lifecycle Engine: proposal, onboarding, invoice and payment follow-up, from one client list.

Every run looks at where each client is and does only the next step:
  lead           -> proposal + cover email
  signed         -> welcome email, kickoff agenda, project checklist, deposit invoice (PDF) + invoice email
  invoice unpaid -> friendly reminder after 7 days, a second one after 14, then a flag to call
  paid           -> nothing to chase
Dates, amounts and invoice numbers are decided by code. Claude only writes the words.
Nothing is sent: every email lands in output/outbox/ as a draft for approval.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fpdf import FPDF
from pydantic import BaseModel

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

STUDIO = "AutomationLogics"
SENDER = "Gabriella"
DEPOSIT = 0.5           # 50% to start, 50% on delivery
PAYMENT_TERMS_DAYS = 7  # invoice due one week after it is issued
REMINDER_DAYS = (7, 14) # reminders this many days after the invoice, then a call
PROPOSAL_VALID_DAYS = 14

TODAY = date.fromisoformat(os.getenv("TODAY") or date.today().isoformat())
OUT = HERE / "output"
STATE_FILE = OUT / "state.json"

VOICE = f"""You write for {STUDIO}, an automation consultancy for women who run small businesses.
Plain, warm and direct English. Short sentences. No hype, no buzzwords.
Use only the facts you are given. Never invent prices, dates, tools or promises.
Emails are signed "{SENDER}"."""

PROPOSAL_SYSTEM = VOICE + """
Write a short proposal from the meeting notes.
Say what will be done and what the client gets, never how it is built: no step by step, no technical recipe.
Do not write prices or payment terms, the system adds them."""

ONBOARDING_SYSTEM = VOICE + """
The client just signed. Write the welcome email, the kickoff agenda and the project checklist.
Checklist owners are "client" or "us". due_in_days counts from the signing date.
Also write the email that goes with the deposit invoice, using the invoice facts exactly as given."""

REMINDER_SYSTEM = VOICE + """
Write a payment reminder for an unpaid invoice, using the invoice facts exactly as given.
First reminder: light and friendly, assume it slipped through.
Second reminder: still kind, a little clearer, and offer to help if something is wrong."""


class Proposal(BaseModel):
    title: str
    opening: str
    what_we_heard: list[str]
    what_we_will_do: list[str]
    what_you_get: list[str]
    timeline: str
    not_included: list[str]
    email_subject: str
    email_body: str


class Task(BaseModel):
    task: str
    owner: Literal["client", "us"]
    due_in_days: int


class Onboarding(BaseModel):
    welcome_subject: str
    welcome_body: str
    kickoff_agenda: list[str]
    checklist: list[Task]
    invoice_subject: str
    invoice_body: str


class Email(BaseModel):
    subject: str
    body: str


def money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def draft(kind: str, client: dict, subject: str, body: str, attachment: str = "") -> str:
    """Save an email as a draft in the outbox. Nothing is sent."""
    name = f"{TODAY.isoformat()}-{client['id']}-{kind}.md"
    lines = [f"**To:** {client['contact']} <{client['email']}>", f"**Subject:** {subject}"]
    if attachment:
        lines.append(f"**Attachment:** {attachment}")
    lines += ["**Status:** draft, waiting for approval", "", body]
    write(OUT / "outbox" / name, "\n".join(lines))
    return name


def do_proposal(c: dict, notes: str, st: dict) -> None:
    p = ask(PROPOSAL_SYSTEM, f"Client: {c['company']} ({c['contact']})\nProject: {c['project']}\n\nMeeting notes:\n{notes}", Proposal)
    deposit = c["price"] * DEPOSIT
    valid = TODAY + timedelta(days=PROPOSAL_VALID_DAYS)
    doc = [
        f"# {p.title}",
        f"**For:** {c['contact']}, {c['company']} · **From:** {SENDER}, {STUDIO} · **Date:** {TODAY.isoformat()}",
        "",
        p.opening,
        "",
        "## What we heard",
        *[f"- {x}" for x in p.what_we_heard],
        "",
        "## What we will do",
        *[f"- {x}" for x in p.what_we_will_do],
        "",
        "## What you get",
        *[f"- {x}" for x in p.what_you_get],
        "",
        "## Timeline",
        p.timeline,
        "",
        "## Not included",
        *[f"- {x}" for x in p.not_included],
        "",
        "## Investment",
        f"- **Total:** {money(c['price'], c['currency'])}",
        f"- **To start:** {money(deposit, c['currency'])} ({int(DEPOSIT * 100)}%), the rest on delivery",
        f"- **Valid until:** {valid.isoformat()}",
    ]
    write(OUT / c["id"] / "proposal.md", "\n".join(doc))
    draft("proposal", c, p.email_subject, p.email_body, "proposal.md")
    st["proposal_sent"] = TODAY.isoformat()


def next_invoice_number(state: dict) -> str:
    used = [s["invoice"]["number"] for s in state.values() if s.get("invoice")]
    return f"INV-{TODAY.year}-{len(used) + 1:03d}"


def invoice_pdf(path: Path, c: dict, inv: dict) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=18)
    pdf.cell(0, 10, STUDIO, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for line in [
        "",
        f"INVOICE {inv['number']}",
        f"Issue date: {inv['issued']}    Due date: {inv['due']}",
        f"Bill to: {c['company']}, {c['contact']}",
        "",
        f"{c['project']}, deposit {int(DEPOSIT * 100)}%",
        f"   {money(inv['amount'], c['currency'])}",
        "",
        f"TOTAL DUE: {money(inv['amount'], c['currency'])}",
        "",
        "Fictional sample invoice generated by the Client Lifecycle Engine.",
    ]:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    print(f"  wrote {path}")


def do_onboarding(c: dict, notes: str, st: dict, state: dict) -> None:
    signed = date.fromisoformat(c["signed_on"])
    inv = {
        "number": next_invoice_number(state),
        "issued": signed.isoformat(),
        "due": (signed + timedelta(days=PAYMENT_TERMS_DAYS)).isoformat(),
        "amount": round(c["price"] * DEPOSIT, 2),
    }
    facts = (
        f"Client: {c['company']} ({c['contact']})\nProject: {c['project']}\nSigned on: {signed.isoformat()}\n"
        f"Deposit invoice: {inv['number']}, {money(inv['amount'], c['currency'])}, due {inv['due']}\n\n"
        f"Meeting notes:\n{notes}"
    )
    o = ask(ONBOARDING_SYSTEM, facts, Onboarding)
    doc = [
        f"# Onboarding · {c['company']}",
        f"Signed on {signed.isoformat()} · project: {c['project']}",
        "",
        "## Kickoff agenda",
        *[f"{i}. {x}" for i, x in enumerate(o.kickoff_agenda, 1)],
        "",
        "## Project checklist",
        "| Task | Owner | Due |",
        "|---|---|---|",
        *[f"| {t.task} | {t.owner} | {(signed + timedelta(days=t.due_in_days)).isoformat()} |" for t in o.checklist],
    ]
    write(OUT / c["id"] / "onboarding.md", "\n".join(doc))
    pdf_name = f"invoice-{inv['number']}.pdf"
    invoice_pdf(OUT / c["id"] / pdf_name, c, inv)
    if not c["paid_on"]:  # already paid: keep the records, skip emails that would arrive late
        draft("welcome", c, o.welcome_subject, o.welcome_body)
        draft("invoice", c, o.invoice_subject, o.invoice_body, pdf_name)
    st["onboarded"] = TODAY.isoformat()
    st["invoice"] = inv
    st.setdefault("reminders", [])


def do_reminder(c: dict, st: dict, n: int, days: int) -> None:
    inv = st["invoice"]
    facts = (
        f"Client: {c['company']} ({c['contact']})\nInvoice: {inv['number']}, {money(inv['amount'], c['currency'])}\n"
        f"Issued {inv['issued']}, due {inv['due']}, unpaid after {days} days.\nThis is reminder number {n}."
    )
    e = ask(REMINDER_SYSTEM, facts, Email)
    draft(f"reminder-{n}", c, e.subject, e.body)
    st["reminders"].append(TODAY.isoformat())


def stage(c: dict, st: dict) -> tuple[str, str]:
    """Where the client is and what happens next, for the pipeline board."""
    if c["paid_on"]:
        return "paid", f"Deposit paid on {c['paid_on']}. Next: build and deliver."
    if st.get("invoice"):
        days = (TODAY - date.fromisoformat(st["invoice"]["issued"])).days
        sent = len(st["reminders"])
        if sent >= len(REMINDER_DAYS):
            return "overdue", f"Unpaid after {days} days and {sent} reminders. Call {c['contact']}."
        nxt = date.fromisoformat(st["invoice"]["issued"]) + timedelta(days=REMINDER_DAYS[sent])
        return "invoiced", f"Unpaid for {days} days, {sent} reminder(s) sent. Next reminder on {nxt.isoformat()}."
    if c["signed_on"]:
        return "signed", "Onboarding on the next run."
    if st.get("proposal_sent"):
        return "proposal sent", f"Waiting for {c['contact']} to sign (sent {st['proposal_sent']})."
    return "lead", "Proposal on the next run."


def main() -> None:
    clients = json.loads((HERE / "data" / "clients.json").read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    print(f"Today: {TODAY.isoformat()} · {len(clients)} clients")

    for c in clients:
        st = state.setdefault(c["id"], {})
        notes = (ROOT / c["notes"]).read_text(encoding="utf-8")
        actions = []
        if not c["signed_on"] and not st.get("proposal_sent"):
            actions.append("proposal")
        if c["signed_on"] and not st.get("onboarded"):
            actions.append("onboarding + deposit invoice")
        print(f"- {c['company']}: {', '.join(actions) or 'no new document, payment check only'}")
        if DRY_RUN:
            continue

        if "proposal" in actions:
            do_proposal(c, notes, st)
        if actions and actions[-1].startswith("onboarding"):
            do_onboarding(c, notes, st, state)
        if st.get("invoice") and not c["paid_on"]:
            days = (TODAY - date.fromisoformat(st["invoice"]["issued"])).days
            n = len(st["reminders"])
            if n < len(REMINDER_DAYS) and days >= REMINDER_DAYS[n]:
                do_reminder(c, st, n + 1, days)

    if DRY_RUN:
        print("DRY RUN: no API key, nothing written.")
        return

    board = [
        "# Client pipeline",
        "",
        f"_Last run: {run_stamp()} · today is {TODAY.isoformat()} · fictional clients_",
        "",
        "| Client | Stage | What happens next | Files |",
        "|---|---|---|---|",
    ]
    for c in clients:
        name, nxt = stage(c, state[c["id"]])
        folder = OUT / c["id"]
        files = " · ".join(f"[{f.name}]({c['id']}/{f.name})" for f in sorted(folder.glob("*"))) if folder.exists() else ""
        board.append(f"| {c['company']} | **{name}** | {nxt} | {files} |")
    board += ["", "Email drafts waiting for approval: [outbox/](outbox)"]
    write(OUT / "pipeline.md", "\n".join(board))
    write(STATE_FILE, json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
