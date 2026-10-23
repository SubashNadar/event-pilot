"""Final-plan exports: a PPTX brochure and a PDF blueprint, built from the saved plan.

Colours follow the Event Pilot green palette so exports match the app.
"""

import io
import re
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.agents.fmt import inr
from app.models.event import EventBrief, EventPlan

GREEN = "19756D"
GREEN_DARK = "0F5A54"
LIME = "D7ED74"
INK = "172D2B"
MUTED = "647370"
WASH = "F4F7F5"


def _register_fonts() -> tuple[str, str]:
    """Helvetica has no rupee sign, so use Arial (or another TrueType font with ₹) when it's available."""
    candidates = [("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"), ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    for regular, bold in candidates:
        try:
            pdfmetrics.registerFont(TTFont("EventPilot", regular))
            pdfmetrics.registerFont(TTFont("EventPilot-Bold", bold))
            return "EventPilot", "EventPilot-Bold"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


def _clean(text: str | None) -> str:
    """Plain text from the model's markdown: no headings, bold markers or bullets."""
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[*#`]", "", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _when(event: EventBrief) -> str:
    return f"{event.event_date.strftime('%d %b %Y')} · {event.location} · {event.attendees} guests"


def _rgb(hex_value: str) -> RGBColor:
    return RGBColor.from_string(hex_value)


# ------------------------------------------------------------------ PPTX brochure

def _slide_title(prs: Presentation, text: str, kicker: str = "") -> Any:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(1.1))
    band.fill.solid()
    band.fill.fore_color.rgb = _rgb(GREEN)
    band.line.fill.background()
    box = slide.shapes.add_textbox(Inches(0.6), Inches(0.2), prs.slide_width - Inches(1.2), Inches(0.8))
    frame = box.text_frame
    if kicker:
        para = frame.paragraphs[0]
        para.text = kicker.upper()
        para.font.size = Pt(11)
        para.font.color.rgb = _rgb(LIME)
    title_para = frame.add_paragraph() if kicker else frame.paragraphs[0]
    title_para.text = text
    title_para.font.size = Pt(26)
    title_para.font.bold = True
    title_para.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    return slide


def _bullets(slide: Any, items: list[str], left: float, top: float, width: float, height: float, size: int = 16) -> None:
    frame = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height)).text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        para.text = item
        para.font.size = Pt(size)
        para.font.color.rgb = _rgb(INK)
        para.space_after = Pt(8)


def _table(slide: Any, header: list[str], rows: list[list[str]], left: float, top: float, width: float, col_widths: list[float] | None = None) -> None:
    shape = slide.shapes.add_table(len(rows) + 1, len(header), Inches(left), Inches(top), Inches(width), Inches(0.4 * (len(rows) + 1)))
    table = shape.table
    for col, label in enumerate(header):
        cell = table.cell(0, col)
        cell.text = label
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(GREEN_DARK)
        cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.text_frame.paragraphs[0].font.bold = True
        cell.text_frame.paragraphs[0].font.size = Pt(13)
    for row_index, row in enumerate(rows, start=1):
        for col, value in enumerate(row):
            cell = table.cell(row_index, col)
            cell.text = value
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(WASH if row_index % 2 else "FFFFFF")
            cell.text_frame.paragraphs[0].font.size = Pt(12)
            cell.text_frame.paragraphs[0].font.color.rgb = _rgb(INK)
    if col_widths:
        for col, w in enumerate(col_widths):
            table.columns[col].width = Inches(w)


def build_pptx(event: EventBrief, plan: EventPlan) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    width = 13.333

    # Cover
    cover = prs.slides.add_slide(prs.slide_layouts[6])
    background = cover.background.fill
    background.solid()
    background.fore_color.rgb = _rgb(GREEN_DARK)
    box = cover.shapes.add_textbox(Inches(0.9), Inches(2.3), Inches(11.5), Inches(3))
    frame = box.text_frame
    frame.word_wrap = True
    kicker = frame.paragraphs[0]
    kicker.text = "EVENT PILOT · FINAL PLAN BROCHURE"
    kicker.font.size = Pt(13)
    kicker.font.color.rgb = _rgb(LIME)
    title = frame.add_paragraph()
    title.text = event.name
    title.font.size = Pt(44)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    line = frame.add_paragraph()
    line.text = _when(event)
    line.font.size = Pt(18)
    line.font.color.rgb = _rgb("E6EFEC")

    # Overview
    slide = _slide_title(prs, "The plan at a glance", "Overview")
    _bullets(slide, [
        f"Event type: {plan.plan_type}",
        f"Venue: {plan.venue}",
        f"Budget: {inr(event.budget)} approved · {inr(plan.budget_forecast)} forecast",
        f"Plan confidence: {plan.confidence}%",
        f"Objective: {event.objective}",
    ], 0.6, 1.5, width - 1.2, 5, 18)

    # Venue
    slide = _slide_title(prs, plan.venue, "Venue")
    _bullets(slide, [plan.venue_detail or "Venue details to be confirmed.", "Confirm availability and get a written quotation before booking."], 0.6, 1.5, width - 1.2, 4, 18)

    # Budget
    slide = _slide_title(prs, "Budget", "Money")
    rows = [[line.category, inr(line.amount), f"{line.share_percent}%"] for line in plan.budget_lines]
    rows.append(["Total forecast", inr(plan.budget_forecast), "100%"])
    _table(slide, ["Category", "Amount", "Share"], rows, 0.6, 1.5, width - 1.2, [6.5, 3.5, 2.0])

    # Agenda
    slide = _slide_title(prs, "Event-day agenda", "Schedule")
    rows = [[item.time, item.activity, item.owner] for item in plan.agenda]
    _table(slide, ["Time", "Activity", "Owner"], rows, 0.6, 1.5, width - 1.2, [2.2, 6.8, 3.0])

    # Risks
    slide = _slide_title(prs, "Risks and how we handle them", "Risk")
    rows = [[risk.level, risk.title, risk.recommended_action] for risk in plan.risks]
    _table(slide, ["Level", "Risk", "Action"], rows, 0.6, 1.5, width - 1.2, [1.6, 4.8, 5.9])

    # Next steps
    slide = _slide_title(prs, "Next steps", "Recommendations")
    steps = [line for line in _clean(plan.recommendations).splitlines()][:8] or ["Review the plan with your team and confirm the venue."]
    _bullets(slide, steps, 0.6, 1.4, width - 1.2, 5.6, 16)

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ PDF blueprint

def build_pdf(event: EventBrief, plan: EventPlan) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=f"{event.name} — blueprint")
    base = getSampleStyleSheet()
    regular, bold = _register_fonts()
    green = colors.HexColor(f"#{GREEN}")
    h1 = ParagraphStyle("h1", parent=base["Title"], fontName=bold, textColor=colors.HexColor(f"#{GREEN_DARK}"), alignment=0, fontSize=22, leading=26)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontName=bold, textColor=green, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=base["BodyText"], fontName=regular, textColor=colors.HexColor(f"#{INK}"), fontSize=10, leading=14)
    muted = ParagraphStyle("muted", parent=body, textColor=colors.HexColor(f"#{MUTED}"))

    def grid(data: list[list[str]], widths: list[float]) -> Table:
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{GREEN_DARK}")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("FONTNAME", (0, 1), (-1, -1), regular),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(f"#{WASH}")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DCE5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return table

    story: list[Any] = [
        Paragraph(event.name, h1),
        Paragraph(_when(event), muted),
        Paragraph(f"Objective: {event.objective}", body),
        Spacer(1, 6),
        Paragraph(f"Venue: {plan.venue}", h2),
        Paragraph(plan.venue_detail or "Venue details to be confirmed.", body),
        Paragraph(f"Budget: {inr(event.budget)} approved · {inr(plan.budget_forecast)} forecast · confidence {plan.confidence}%", h2),
        grid([["Category", "Amount", "Share"]] + [[line.category, inr(line.amount), f"{line.share_percent}%"] for line in plan.budget_lines] + [["Total forecast", inr(plan.budget_forecast), "100%"]], [90 * mm, 50 * mm, 30 * mm]),
        Paragraph("Event-day agenda", h2),
        grid([["Time", "Activity", "Owner"]] + [[item.time, item.activity, item.owner] for item in plan.agenda], [28 * mm, 100 * mm, 40 * mm]),
        Paragraph("Risks and actions", h2),
        grid([["Level", "Risk", "Action"]] + [[risk.level, risk.title, risk.recommended_action] for risk in plan.risks], [20 * mm, 60 * mm, 88 * mm]),
        Paragraph("Next steps", h2),
    ]
    for line in _clean(plan.recommendations).splitlines()[:8]:
        story.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), body))
    doc.build(story)
    return buffer.getvalue()
