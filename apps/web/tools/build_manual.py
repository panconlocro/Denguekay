#!/usr/bin/env python3
"""Build the user manual from the same Spanish content as HelpPage.

Run with a Python environment containing reportlab and pypdf:
    python apps/web/tools/build_manual.py
The output is apps/web/public/manual-usuario.pdf; no network access is needed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

WEB = Path(__file__).resolve().parents[1]
SOURCE = WEB / "src" / "content" / "help.json"
OUTPUT = WEB / "public/manual-usuario.pdf"
WIDTH, HEIGHT = A4
MARGIN = 44
CONTENT_WIDTH = WIDTH - 2 * MARGIN


def build_manual() -> None:
    content = json.loads(SOURCE.read_text(encoding="utf-8"))
    manual = content["manual"]
    pages = manual["pages"]
    # Reuse the web palette without maintaining a second set of brand colors.
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]+)",
                            (WEB / "src" / "tokens.css").read_text(encoding="utf-8")))
    palette = {key: colors.HexColor(value) for key, value in tokens.items()}
    font_dir = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Manual", str(font_dir / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("ManualBold", str(font_dir / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("Manual", normal="Manual", bold="ManualBold")

    body = ParagraphStyle("Body", fontName="Manual", fontSize=9.7,
                          leading=14.4, textColor=palette["ink"], spaceAfter=8,
                          alignment=TA_LEFT)
    heading = ParagraphStyle("Heading", parent=body, fontName="ManualBold",
                             fontSize=13, leading=17, textColor=palette["primary"],
                             spaceBefore=10, spaceAfter=8, keepWithNext=True)
    small = ParagraphStyle("Small", parent=body, fontSize=8.4, leading=12,
                           textColor=palette["muted"], spaceAfter=0)
    step = ParagraphStyle("Step", parent=body, leftIndent=21, firstLineIndent=-17,
                          spaceAfter=6)
    question = ParagraphStyle("Question", parent=body, fontName="ManualBold",
                              spaceBefore=5, spaceAfter=3, keepWithNext=True)

    def paragraph(text: str, style: ParagraphStyle = body) -> Paragraph:
        # Content is plain text, not trusted ReportLab markup.
        return Paragraph(escape(text), style)

    def callout(text: str) -> Table:
        box = Table([[paragraph(text, small)]], colWidths=[CONTENT_WIDTH])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), palette["canvas"]),
            ("LINEBEFORE", (0, 0), (0, -1), 3, palette["primary"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 13),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        return box

    def decorate(canvas, doc):
        index = doc.page - 1
        if index >= len(pages):
            raise ValueError("Manual overflow: revise spacing before publishing.")
        page = pages[index]
        canvas.saveState()
        canvas.setTitle(f"{manual['brand']} | {manual['title']}")
        canvas.setAuthor(manual["brand"])
        canvas.setSubject(manual["scope"])
        canvas.setFillColor(palette["sidebar"])
        canvas.rect(0, HEIGHT - 91, WIDTH, 91, fill=1, stroke=0)
        canvas.setFillColor(palette["primary"])
        canvas.roundRect(MARGIN, HEIGHT - 63, 30, 30, 8, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.circle(MARGIN + 15, HEIGHT - 48, 6, fill=1, stroke=0)
        canvas.setFillColor(palette["canvas"])
        canvas.circle(MARGIN + 21, HEIGHT - 42, 2.5, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("ManualBold", 17)
        canvas.drawString(MARGIN + 42, HEIGHT - 46, manual["brand"])
        canvas.setFont("Manual", 8)
        canvas.drawString(MARGIN + 42, HEIGHT - 62, manual["scope"])
        canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 42, manual["title"])
        canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 58, manual["edition"])
        canvas.setFillColor(palette["primary"])
        canvas.setFont("ManualBold", 9)
        canvas.drawString(MARGIN, HEIGHT - 119, f"0{doc.page} / 0{len(pages)}")
        canvas.setFillColor(palette["ink"])
        canvas.setFont("ManualBold", 23)
        canvas.drawString(MARGIN, HEIGHT - 150, page["title"])
        canvas.setFillColor(palette["muted"])
        canvas.setFont("Manual", 9)
        canvas.drawString(MARGIN, HEIGHT - 169, page["subtitle"])
        canvas.setStrokeColor(palette["border"])
        canvas.line(MARGIN, 49, WIDTH - MARGIN, 49)
        canvas.setFont("Manual", 8)
        canvas.drawString(MARGIN, 33, f"{manual['brand']} · {manual['title']}")
        canvas.drawRightString(WIDTH - MARGIN, 33, f"{doc.page} / {len(pages)}")
        destination = f"manual-page-{doc.page}"
        canvas.bookmarkPage(destination)
        canvas.addOutlineEntry(page["title"], destination, level=0)
        canvas.restoreState()

    story = []
    for page_number in range(1, len(pages) + 1):
        if page_number > 1:
            story.append(PageBreak())
        if page_number == 1:
            story.extend([callout(manual["notice"]), Spacer(1, 5)])
        for topic in content["topics"]:
            if topic["page"] != page_number:
                continue
            story.append(paragraph(topic["title"], heading))
            story.extend(paragraph(text) for text in topic["paragraphs"])
            for index, text in enumerate(topic["steps"], 1):
                story.append(paragraph(f"{index}. {text}", step))
            if topic.get("liveLegend"):
                story.extend([callout(manual["legendNote"]), Spacer(1, 3)])
        if page_number == len(pages):
            troubleshooting = content["troubleshooting"]
            story.append(paragraph(troubleshooting["title"], heading))
            for item in troubleshooting["items"]:
                story.append(KeepTogether([
                    paragraph(item["question"], question),
                    paragraph(item["answer"]),
                ]))
            story.append(paragraph(content["support"]["title"], heading))
            story.extend(paragraph(text) for text in content["support"]["paragraphs"])
            story.extend([Spacer(1, 7), callout(content["support"]["status"])])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = BaseDocTemplate(str(OUTPUT), pagesize=A4,
                               title=f"{manual['brand']} | {manual['title']}",
                               author=manual["brand"], pageCompression=1,
                               invariant=1)
    frame = Frame(MARGIN, 65, CONTENT_WIDTH, HEIGHT - 251,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document.addPageTemplates(PageTemplate(id="Manual", frames=[frame], onPage=decorate))
    document.build(story)

    reader = PdfReader(OUTPUT)
    if len(reader.pages) != len(pages):
        raise ValueError(f"Expected {len(pages)} pages, got {len(reader.pages)}")
    # Verify the full shared prose survived pagination and font encoding.
    def compact(text: str) -> str:
        return " ".join(text.split())

    for number, page in enumerate(reader.pages, 1):
        text = compact(page.extract_text())
        expected = [topic for topic in content["topics"] if topic["page"] == number]
        for topic in expected:
            for snippet in [topic["title"], *topic["paragraphs"], *topic["steps"]]:
                if compact(snippet) not in text:
                    raise ValueError(f"Missing content on page {number}: {snippet[:60]}")
        if f"{number} / {len(pages)}" not in text:
            raise ValueError(f"Missing page footer: {number}")
    final_text = compact(reader.pages[-1].extract_text())
    for snippet in [*content["support"]["paragraphs"], content["support"]["status"]]:
        if compact(snippet) not in final_text:
            raise ValueError("Missing support content")
    print(f"Created {OUTPUT} ({len(reader.pages)} pages; shared text verified)")


if __name__ == "__main__":
    build_manual()
