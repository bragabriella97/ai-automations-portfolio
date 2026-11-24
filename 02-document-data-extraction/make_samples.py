"""Creates the fictional sample documents in data/. Run once: python make_samples.py (needs fpdf2)."""

from pathlib import Path

from fpdf import FPDF

DATA = Path(__file__).parent / "data"

DOCS = {
    "invoice-luz-design.pdf": [
        ("LUZ DESIGN STUDIO", 16),
        ("Rua Exemplo 21, Lisboa · NIF 000 000 000 (sample)", 9),
        ("", 6),
        ("INVOICE  N.  LD-2026-087", 13),
        ("Issue date: 3 November 2026      Due date: 3 December 2026", 10),
        ("Bill to: Ana Costa Coaching", 10),
        ("", 6),
        ("Brand identity package ............ 1 x 950.00 EUR = 950.00 EUR", 10),
        ("Social media templates (10) ....... 1 x 250.00 EUR = 250.00 EUR", 10),
        ("Extra revision round .............. 2 x 60.00 EUR = 120.00 EUR", 10),
        ("", 6),
        ("Subtotal: 1,320.00 EUR", 10),
        ("VAT 23%: 303.60 EUR", 10),
        ("TOTAL: 1,623.60 EUR", 12),
    ],
    "receipt-cafe-central.pdf": [
        ("Cafe Central", 14),
        ("Av. Exemplo 100", 9),
        ("Receipt 00412 - 18/11/2026 10:42", 10),
        ("", 6),
        ("2 Cappuccino     2 x 2.80   5.60", 10),
        ("1 Croissant      1 x 1.90   1.90", 10),
        ("1 Orange juice   1 x 3.50   3.50", 10),
        ("", 6),
        ("Total EUR 11.00 (VAT incl. 6%: 0.62)", 11),
        ("Paid by card", 9),
    ],
    "invoice-nuvem-hosting.pdf": [
        ("Nuvem Hosting Ltd.", 15),
        ("Invoice #NH-55021", 12),
        ("Date: 2026-11-01", 10),
        ("Customer: Ana Costa Coaching", 10),
        ("", 6),
        ("Business hosting plan, November 2026 ... 1 x 24.90 USD = 24.90 USD", 10),
        ("Domain renewal anacosta.example ....... 1 x 15.00 USD = 15.00 USD", 10),
        ("", 6),
        ("Total due: 39.90 USD", 12),
        ("Payment due upon receipt", 9),
    ],
}


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for name, lines in DOCS.items():
        pdf = FPDF()
        pdf.add_page()
        for text, size in lines:
            pdf.set_font("Helvetica", size=size)
            pdf.cell(0, size * 0.7, text, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(DATA / name))
        print("created", name)


if __name__ == "__main__":
    main()
