"""Lead Enrichment Intelligence: read a lead's website and turn it into a fit score and a real pitch angle."""

import csv
import json
import sys
from pathlib import Path
from typing import Literal

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

MAX_CHARS = 15000  # keep each page to a sensible size for one request

SYSTEM = """You are a B2B research assistant for an automation and AI consultancy.
You get the visible text of a company's homepage.
Base every answer only on that text. If the text is too thin to judge, say so and give fit_score 0.
manual_work_signals are processes that usually run by hand at a business like this
(bookings, onboarding, invoicing, support, reporting), grounded in what the site shows.
pitch_angle is one opening sentence that mentions something specific from the page."""


class Insight(BaseModel):
    what_they_do: str
    audience: str
    team_size_guess: Literal["solo", "small", "medium", "large", "unknown"]
    manual_work_signals: list[str]  # up to 3
    fit_score: int  # 0 to 10
    pitch_angle: str


def page_text(url: str) -> str:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (lead-research-demo)"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")  # bytes, so the page encoding is detected correctly
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:MAX_CHARS]


def main() -> None:
    with open(HERE / "data" / "leads.csv", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    if DRY_RUN:
        print(f"DRY RUN: {len(leads)} leads loaded, no API key, nothing sent.")
        return

    results = []
    for lead in leads:
        print(f"- {lead['company']}")
        try:
            text = page_text(lead["website"])
        except requests.RequestException as err:
            print(f"  could not open the site: {err}")
            results.append({**lead, "error": "website not reachable"})
            continue
        insight = ask(SYSTEM, f"Company: {lead['company']}\nWebsite: {lead['website']}\n\nPage text:\n{text}", Insight)
        results.append({**lead, **insight.model_dump()})

    out = HERE / "output"
    write(out / "enriched.json", json.dumps(results, indent=2, ensure_ascii=False))

    lines = [
        "# Enriched leads",
        "",
        f"_Last run: {run_stamp()} · {len(results)} leads · public websites, read live_",
        "",
    ]
    for r in sorted(results, key=lambda r: -r.get("fit_score", -1)):
        lines.append(f"## {r['company']} · fit {r.get('fit_score', 'n/a')}/10")
        if "error" in r:
            lines += [f"Skipped: {r['error']}", ""]
            continue
        lines += [
            f"- **What they do:** {r['what_they_do']}",
            f"- **Audience:** {r['audience']}",
            f"- **Team size:** {r['team_size_guess']}",
            "- **Manual work:**",
            *[f"  - {s}" for s in r["manual_work_signals"]],
            f"- **Pitch angle:** {r['pitch_angle']}",
            "",
        ]
    write(out / "enriched.md", "\n".join(lines))


if __name__ == "__main__":
    main()
