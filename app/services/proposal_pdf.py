"""Versioned Skylix proposal PDF rendering from immutable pricebook data."""

from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models import Artifact, Business, Proposal
from app.services.artifact_storage import persist_artifact
from app.services.config_loader import load
from app.services.events import record_event


FONT_NAME = "PipelineVera"
FONT_BOLD_NAME = "PipelineVeraBold"
HEADER_COLOR = colors.HexColor("#F3F2F0")
GRID_COLOR = colors.HexColor("#E4E2DE")


def _register_fonts() -> tuple[str, str]:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if FONT_NAME not in registered:
        font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, str(font_dir / "VeraBd.ttf")))
    return FONT_NAME, FONT_BOLD_NAME


def _text(value: object, fallback: str = "-") -> str:
    value = str(value or "").strip()
    return escape(value) if value else fallback


def _price(package: dict) -> str:
    low = package.get("price_from_eur")
    high = package.get("price_to_eur")
    if high is not None:
        return f"{low} - {high} €"
    return f"{low} €" if low is not None else "On request"


def _addon_price(addon: dict) -> str:
    values = addon.get("range_eur") or []
    return f"+ {values[0]} - {values[1]} €" if len(values) == 2 else "On request"


def _styles() -> tuple[dict[str, ParagraphStyle], str, str]:
    font, bold = _register_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ProposalTitle", parent=base["Title"], fontName=bold, fontSize=25, leading=31, spaceAfter=18),
        "link": ParagraphStyle("ProposalLink", parent=base["Normal"], fontName=font, fontSize=10, leading=14, underlineWidth=0.5, spaceAfter=10),
        "label": ParagraphStyle("ProposalLabel", parent=base["Normal"], fontName=bold, fontSize=10, leading=14, spaceAfter=15),
        "section": ParagraphStyle("ProposalSection", parent=base["Heading2"], fontName=bold, fontSize=16, leading=20, spaceBefore=10, spaceAfter=10),
        "subsection": ParagraphStyle("ProposalSubsection", parent=base["Heading3"], fontName=bold, fontSize=13, leading=17, spaceBefore=8, spaceAfter=7),
        "body": ParagraphStyle("ProposalBody", parent=base["BodyText"], fontName=font, fontSize=9.2, leading=13),
        "body_bold": ParagraphStyle("ProposalBodyBold", parent=base["BodyText"], fontName=bold, fontSize=9.2, leading=13),
        "note": ParagraphStyle("ProposalNote", parent=base["Normal"], fontName=font, fontSize=10, leading=14, spaceBefore=8, spaceAfter=8),
        "note_bold": ParagraphStyle("ProposalNoteBold", parent=base["Normal"], fontName=bold, fontSize=10, leading=14, spaceBefore=8, spaceAfter=8),
    }, font, bold


def _cell(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _table(headers: list[str], rows: list[list[object]], widths: list[float], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[_cell(header, styles["body"]) for header in headers]]
    for row in rows:
        data.append([_cell(value, styles["body"]) for value in row])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _footer(title: str, font: str):
    def draw(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#8B8B8B"))
        canvas.drawString(document.leftMargin, 11 * mm, title)
        canvas.drawRightString(A4[0] - document.rightMargin, 11 * mm, str(document.page))
        canvas.restoreState()
    return draw


def render_proposal_pdf(proposal: Proposal) -> bytes:
    """Render the canonical four-page agency proposal without model calls."""
    content = proposal.content or {}
    pricebook = load("pricebook", proposal.pricebook_version)
    layout = pricebook["proposal_layout"]
    packages = pricebook["packages"]
    addons = pricebook["addons"]
    styles, font, _ = _styles()
    business_name = _text(content.get("business"), "Business")
    document_title = f"Business Proposal to {business_name}"

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title=document_title,
        author=layout["agency_website"],
    )
    width = A4[0] - document.leftMargin - document.rightMargin
    header_path = PROJECT_ROOT / layout["header_asset"]
    story = []
    if header_path.is_file():
        header = Image(str(header_path), width=width, height=width * 627 / 2776)
        story.extend([header, Spacer(1, 4)])
    story.extend([
        Paragraph(document_title, styles["title"]),
        Paragraph(layout["agency_website"], styles["link"]),
        Paragraph(layout["price_list_label"], styles["label"]),
        Paragraph("1. Main Packages", styles["section"]),
    ])
    package_rows = []
    for key in ("basic", "local_pro", "automation_pro"):
        package = packages[key]
        package_rows.append([package["label"], package["scope"], _price(package), package["ideal_for"]])
    story.extend([
        _table(["Package", "What is included", "One-time price (from)", "Ideal for"], package_rows, [31 * mm, 57 * mm, 34 * mm, 47 * mm], styles),
        Paragraph("2. Detailed Features and Add-ons", styles["section"]),
        Paragraph("2.1 Website (Base)", styles["subsection"]),
        PageBreak(),
        _table(["Feature", "Description", "Included in package"], layout["base_features"], [40 * mm, 101 * mm, 27 * mm], styles),
        Paragraph("Price if sold alone: <b>from 300 €</b>", styles["note"]),
        Paragraph("2.2 Google Maps Setup (Google Business Profile)", styles["subsection"]),
        _table(["Feature", "Description", "Extra price (add-on)"], [row + [""] for row in layout["maps_features"]], [38 * mm, 108 * mm, 22 * mm], styles),
        Paragraph(f"Add-on price: <b>{_addon_price(addons['business_profile_map'])}</b>", styles["note"]),
        Paragraph("Included in: <b>Local Pro</b> and <b>Automation Pro</b>", styles["note"]),
        Paragraph("2.3 Online Booking System", styles["subsection"]),
        _table(["Feature", "Description", "Extra price (add-on)"], [layout["booking_features"][0] + [""]], [40 * mm, 101 * mm, 27 * mm], styles),
        PageBreak(),
        _table(["Feature", "Description", "Extra price (add-on)"], [row + [""] for row in layout["booking_features"][1:]], [40 * mm, 101 * mm, 27 * mm], styles),
        Paragraph(f"Add-on price: <b>{_addon_price(addons['online_booking'])}</b>", styles["note"]),
        Paragraph("Included in: <b>Local Pro</b> and <b>Automation Pro</b>", styles["note"]),
        Paragraph("2.4 Simple CRM Setup", styles["subsection"]),
        _table(["Feature", "Description", "Extra price (add-on)"], [row + [""] for row in layout["crm_features"]], [40 * mm, 101 * mm, 27 * mm], styles),
        Paragraph(f"Add-on price: <b>{_addon_price(addons['simple_crm'])}</b>", styles["note"]),
        Paragraph("Included in: <b>Automation Pro</b>", styles["note"]),
        Paragraph("2.5 AI Assistant / WhatsApp Bot (Optional)", styles["subsection"]),
        _table(["Feature", "Description", "Extra price (add-on)"], [row + [""] for row in layout["assistant_features"][:2]], [46 * mm, 95 * mm, 27 * mm], styles),
        PageBreak(),
        _table(["Feature", "Description", "Extra price (add-on)"], [layout["assistant_features"][2] + [""]], [46 * mm, 95 * mm, 27 * mm], styles),
        Paragraph(f"Add-on price: <b>{_addon_price(addons['ai_whatsapp_assistant'])}</b>", styles["note"]),
        Paragraph("Available as: extra option on top of <b>Automation Pro</b> or as future upgrade.", styles["note"]),
        Paragraph("3. Monthly Support Plans (Optional)", styles["section"]),
        _table(
            ["Plan", "What is included", "Monthly price"],
            [["Basic Support", pricebook["support_plans"]["basic_support"]["included"], pricebook["support_plans"]["basic_support"]["price"]], ["Pro Support", pricebook["support_plans"]["pro_support"]["included"], pricebook["support_plans"]["pro_support"]["price"]]],
            [32 * mm, 108 * mm, 28 * mm],
            styles,
        ),
    ])
    document.build(story, onFirstPage=_footer(document_title, font), onLaterPages=_footer(document_title, font))
    return buffer.getvalue()


def ensure_proposal_pdf(db: Session, *, business: Business, proposal: Proposal) -> Artifact:
    """Store one immutable PDF per proposal, returning it on every rerun."""
    existing = (
        db.query(Artifact)
        .filter(Artifact.proposal_id == proposal.id, Artifact.kind == "proposal_pdf", Artifact.deleted_at.is_(None))
        .order_by(Artifact.id.desc())
        .first()
    )
    if existing:
        return existing
    artifact = persist_artifact(
        db,
        business=business,
        proposal=proposal,
        kind="proposal_pdf",
        payload=render_proposal_pdf(proposal),
        filename=f"proposal-{proposal.id}.pdf",
        content_type="application/pdf",
    )
    record_event(
        db,
        action="proposal_pdf_rendered",
        actor="system:proposal_pdf",
        business_id=business.id,
        entity="artifact",
        entity_id=artifact.id,
        config_version=proposal.pricebook_version,
        payload={"proposal_id": proposal.id, "sha256": artifact.sha256},
    )
    return artifact
