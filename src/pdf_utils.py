import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib import colors


def topic_to_filename(topic: str) -> str:
    """Convert a topic string into a safe filename (no extension)."""
    safe = re.sub(r"[^\w\s-]", "", topic).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe or "post"


def save_post_as_pdf(post: str, topic: str, output_dir: str | None = None) -> str:
    """
    Save *post* as a PDF in the Posts/ folder (or *output_dir* if given).
    Uses reportlab — no system fonts needed, works on Windows/Mac/Linux.
    Returns the absolute path of the saved file.
    """
    base = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "Posts")
    os.makedirs(base, exist_ok=True)

    filepath = os.path.join(base, f"{topic_to_filename(topic)}.pdf")

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Normal"],
        fontSize=16,
        leading=22,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#2d2d2d"),
        fontName="Helvetica",
    )

    story = []

    # Title
    story.append(Paragraph(f"LinkedIn Post: {topic}", title_style))
    story.append(Spacer(1, 4 * mm))

    # Divider
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 6 * mm))

    # Post body — each line as its own paragraph to preserve spacing
    for line in post.splitlines():
        text = line.strip()
        if text:
            # Escape XML special characters so reportlab renders them correctly
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 3 * mm))

    doc.build(story)
    return filepath
