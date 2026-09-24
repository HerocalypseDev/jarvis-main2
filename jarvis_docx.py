"""Neatly formatted Word (.docx) files from simple Markdown, used by write_file for .docx names.

Supported: # to #### headings, - / * bullets (indent 2+ spaces to nest), numbered lines (kept as
plain text with their own numbers, so a list restarting at 1 never runs on from an earlier one),
**bold**, *italic*, `code` inline, | tables | (a |---| line under the first row makes it a header),
> quotes, ``` code blocks ```, and a line of just --- for a page break."""
import re

import docx
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Inches

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _base_styles(doc) -> None:
    """House style for a new document: Calibri 11, 1" margins, airy but compact spacing."""
    for s in doc.sections:
        s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(1)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    for level, size in ((1, 18), (2, 14), (3, 12), (4, 11)):
        h = doc.styles[f"Heading {level}"]
        h.font.name = "Calibri"
        h.font.size = Pt(size)
        h.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        h.paragraph_format.space_before = Pt(14 if level == 1 else 10)
        h.paragraph_format.space_after = Pt(4)
        h.paragraph_format.keep_with_next = True


def _add_inline(par, text: str) -> None:
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            par.add_run(part[1:-1]).font.name = "Consolas"
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            par.add_run(part[1:-1]).italic = True
        else:
            par.add_run(part)


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _add_table(doc, rows: list[str]) -> None:
    header = len(rows) > 1 and bool(_TABLE_SEP.match(rows[1]))
    data = [_cells(r) for i, r in enumerate(rows) if not (header and i == 1)]
    ncols = max(len(r) for r in data)
    table = doc.add_table(rows=len(data), cols=ncols)
    table.style = "Table Grid"
    for r, row in enumerate(data):
        for c in range(ncols):
            cell = table.cell(r, c)
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(2)
            _add_inline(par, row[c] if c < len(row) else "")
            if header and r == 0:
                for run in par.runs:
                    run.bold = True
                _shade(cell, "D9E2F3")
    doc.add_paragraph()  # breathing room after the table


def write(path, content: str, append: bool = False) -> None:
    from pathlib import Path

    p = Path(path)
    doc = docx.Document(str(p)) if append and p.exists() else docx.Document()
    if not (append and p.exists()):
        _base_styles(doc)
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.strip().startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Inches(0.3)
            run = par.add_run("\n".join(code))
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            _add_table(doc, rows)
            continue
        elif not line.strip():
            pass
        elif re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif m := re.match(r"^(#{1,4})\s+(.*)", line):
            _add_inline(doc.add_heading(level=len(m.group(1))), m.group(2).strip())
        elif m := re.match(r"^(\s*)[-*•]\s+(.*)", line):
            nested = len(m.group(1).expandtabs(4)) >= 2
            _add_inline(doc.add_paragraph(style="List Bullet 2" if nested else "List Bullet"), m.group(2))
        elif m := re.match(r"^\s*>\s?(.*)", line):
            par = doc.add_paragraph(style="Quote")
            _add_inline(par, m.group(1))
        elif m := re.match(r"^(\s*)(\d+[.)])\s+(.*)", line):
            par = doc.add_paragraph()
            pf = par.paragraph_format
            pf.left_indent = Inches(0.35 + (0.3 if len(m.group(1)) >= 2 else 0))
            pf.first_line_indent = Inches(-0.25)
            pf.space_after = Pt(3)
            _add_inline(par, f"{m.group(2)} {m.group(3)}")
        else:
            _add_inline(doc.add_paragraph(), line.strip())
        i += 1
    doc.save(str(p))
