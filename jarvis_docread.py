"""Text out of Word, PDF and PowerPoint files for read_file.

Found live (2026-10-02): "extract the animes and their release dates from my Word document" (a table) ran out of the 12
agent steps on Gemini. read_file opened the .docx as UTF-8 text, but a .docx is a zip, so the model got gibberish and kept
trying other ways to open it. These readers keep the document's order and render tables as `| cell | cell |` rows, so a
table comes back in one read. Pure functions, no network; a missing library or a broken file returns a plain message.
"""

from __future__ import annotations

from pathlib import Path

DOC_SUFFIXES = {".docx", ".pdf", ".pptx"}
MAX_PDF_PAGES = 60


def _row(cells: list[str]) -> str:
    out: list[str] = []
    for c in cells:
        c = " ".join((c or "").split())
        if not out or c != out[-1]:  # a merged cell shows up once per spanned column
            out.append(c)
    return "| " + " | ".join(out) + " |"


def _docx_text(path: Path) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    lines: list[str] = []
    n_tables = 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(child, doc).text.strip()
            if text:
                lines.append(text)
        elif tag == "tbl":
            n_tables += 1
            lines.append(f"[table {n_tables}]")
            for row in Table(child, doc).rows:
                lines.append(_row([cell.text for cell in row.cells]))
            lines.append("")
    return "\n".join(lines).strip()


def _pdf_text(path: Path) -> str:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages[:MAX_PDF_PAGES], 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"[page {i}]\n{text}")
    if len(reader.pages) > MAX_PDF_PAGES:
        pages.append(f"[only the first {MAX_PDF_PAGES} of {len(reader.pages)} pages were read]")
    return "\n\n".join(pages).strip() or "(this PDF has no text layer: it is probably a scan or pictures)"


def _pptx_text(path: Path) -> str:
    """Slide text straight from the slide XML (python-pptx isn't a dependency): one line per paragraph, slides in order."""
    import re
    import zipfile
    import xml.etree.ElementTree as ET

    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    lines: list[str] = []
    with zipfile.ZipFile(path) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        for n, name in enumerate(slides, 1):
            lines.append(f"[slide {n}]")
            root = ET.fromstring(z.read(name))
            for para in root.iter(ns + "p"):
                text = "".join(t.text or "" for t in para.iter(ns + "t")).strip()
                if text:
                    lines.append(text)
    return "\n".join(lines).strip()


def read_document(path: Path) -> str | None:
    """The text of a .docx/.pdf/.pptx file, or None when `path` is not one of those (read it as plain text)."""
    suffix = path.suffix.lower()
    if suffix not in DOC_SUFFIXES:
        return None
    reader = {".docx": _docx_text, ".pdf": _pdf_text, ".pptx": _pptx_text}[suffix]
    try:
        return reader(path) or "(the document has no text)"
    except ImportError as e:
        return f"Failed to read {path.name}: the library for {suffix} files isn't installed ({e.name})."
    except Exception as e:
        return f"Failed to read {path.name}: {e}"
