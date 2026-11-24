"""Document Data Extraction: PDF invoices and receipts in, clean structured rows out."""

import base64
import csv
import io
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

SYSTEM = """You extract data from business documents for a bookkeeping sheet.
Read only what is printed on the document. Never invent or calculate values that are not there,
except line item amounts when quantity and unit price are both printed.
Dates in YYYY-MM-DD. Use an empty string (or null for amounts) for anything you cannot find.
Set confidence to low if the document is blurry, cut or ambiguous."""


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class Document(BaseModel):
    document_type: Literal["invoice", "receipt", "contract", "other"]
    issuer: str
    document_number: str
    issue_date: str
    due_date: str
    currency: str
    subtotal: float | None
    tax: float | None
    total: float
    line_items: list[LineItem]
    confidence: Literal["high", "medium", "low"]


def main() -> None:
    files = sorted((HERE / "data").glob("*.pdf"))
    if DRY_RUN:
        print(f"DRY RUN: {len(files)} documents found, no API key, nothing sent.")
        return

    rows = []
    for f in files:
        print(f"- {f.name}")
        pdf = base64.standard_b64encode(f.read_bytes()).decode()
        doc = ask(
            SYSTEM,
            [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf}},
                {"type": "text", "text": "Extract this document."},
            ],
            Document,
        )
        rows.append({"file": f.name, **doc.model_dump()})

    out = HERE / "output"
    write(out / "extracted.json", json.dumps(rows, indent=2, ensure_ascii=False))

    cols = ["file", "document_type", "issuer", "document_number", "issue_date", "due_date", "currency", "total", "confidence"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    write(out / "extracted.csv", buf.getvalue())

    lines = [
        "# Extracted documents",
        "",
        f"_Last run: {run_stamp()} · {len(rows)} documents · fictional sample files in `data/`_",
        "",
        "| File | Type | Issuer | Number | Date | Total | Confidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['file']} | {r['document_type']} | {r['issuer']} | {r['document_number']} | "
            f"{r['issue_date']} | {r['total']:,.2f} {r['currency']} | {r['confidence']} |"
        )
    write(out / "extracted.md", "\n".join(lines))


if __name__ == "__main__":
    main()
