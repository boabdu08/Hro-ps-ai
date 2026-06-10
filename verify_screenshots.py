"""
Extract page counts and titles from the HRO Command Center PDFs to verify
what dashboard tab each PDF actually contains, and produce a correct rename map.
"""
import fitz  # PyMuPDF
from pathlib import Path

BASE = Path(r"D:\Hro new dashboard")

# Try to extract text from each PDF
pdfs = sorted(BASE.glob("HRO Command Center*.pdf"), key=lambda p: (len(p.name), p.name))
# Also add Swagger
pdfs.append(BASE / "Hospital AI API - Swagger UI.pdf")

for pdf_path in pdfs:
    try:
        doc = fitz.open(str(pdf_path))
        print(f"\n{pdf_path.name}  [{len(doc)} pages]")
        for i, page in enumerate(doc):
            text = page.get_text("text", clip=(0, 0, 800, 200)).strip()  # top 200px
            lines = [l.strip() for l in text.split('\n') if l.strip()][:6]
            print(f"  P{i+1}: {' | '.join(lines[:4])}")
        doc.close()
    except Exception as e:
        print(f"  ERROR: {e}")
