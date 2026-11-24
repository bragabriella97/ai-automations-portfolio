# AI Automations Portfolio

Hi, I'm **Gabriella Braga**, an automation and AI consultant. I build systems that take repetitive work off small teams: email, documents, research, reporting and content.

Every automation here is real, working code. Each one was run on sample data and the results are saved in its `output/` folder, so you can see exactly what it produced. A GitHub Actions workflow runs them all again with one click.

## Automations

| # | Automation | What it does | Latest result |
|---|---|---|---|
| 01 | [Inbox Zero Agent](01-inbox-zero-agent) | Triages every email and drafts replies for approval | [triage](01-inbox-zero-agent/output/triage.md) |
| 02 | [Document Data Extraction](02-document-data-extraction) | Turns PDF invoices and receipts into clean rows | [extracted](02-document-data-extraction/output/extracted.md) |
| 03 | [Lead Enrichment Intelligence](03-lead-enrichment) | Reads a lead's website and writes a fit score and pitch angle | [enriched](03-lead-enrichment/output/enriched.md) |
| 04 | [Autonomous Report Builder](04-report-builder) | Messy meeting notes to a client report, pending approval | [reports](04-report-builder/output/pending-approval) |
| 05 | [Content Idea Generator](05-content-idea-generator) | Scores real founder questions into an idea bank | [ideas](05-content-idea-generator/output/latest.md) |
| 06 | [Client Lifecycle Engine](06-client-lifecycle) | Proposal, onboarding, deposit invoice and payment reminders | [pipeline](06-client-lifecycle/output/pipeline.md) |
| 07 | [LinkedIn Outreach Engine](07-linkedin-outreach) | 30 day personalised sequence that stops on a no and alerts on a yes | [campaign](07-linkedin-outreach/output/campaign.md) |

## How I build

- **Structured AI output.** Every call to Claude returns data validated against a schema, so the rest of the flow never breaks on free text.
- **Human in the loop where it matters.** Anything that reaches a client or a customer is a draft until a person approves it.
- **Grounded prompts.** The AI only works with what it was given and leaves a field empty instead of guessing.
- **Built to be audited.** Every run leaves a readable trail in `output/`.

## Stack

Python · Claude API (Anthropic SDK, structured outputs, PDF input) · Pydantic · GitHub Actions. I also build the same kind of systems in Make.com, Airtable and Gmail for clients who prefer no-code.

## Run it yourself

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key
python 05-content-idea-generator/run.py
```

Without a key, each script runs in dry mode and only checks its input. All sample data is fictional, except the public websites and community posts that automations 03 and 05 read live.

## Contact

[automationlogics.com](https://www.automationlogics.com)
