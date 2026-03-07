"""
reports/report_generator.py
Turn a list of comparison result dicts into a DataFrame and export formats.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import List

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


_COLUMNS = [
    "identifier",
    "old_file",
    "new_file",
    "old_pages",
    "new_pages",
    "similarity",
    "status",
    "notes",
]

_DISPLAY_COLUMNS = {
    "identifier": "Identifier",
    "old_file":   "Old File",
    "new_file":   "New File",
    "old_pages":  "Old Pages",
    "new_pages":  "New Pages",
    "similarity": "Similarity",
    "status":     "Status",
    "notes":      "Notes",
}

# ── status → (background color, text color) ──────────────────────────────────
_STATUS_COLORS = {
    "SAME":             (colors.HexColor("#d1fae5"), colors.HexColor("#064e3b")),
    "CHANGED":          (colors.HexColor("#fed7aa"), colors.HexColor("#7c2d12")),
    "MISSING_NEW_FILE": (colors.HexColor("#e0e7ff"), colors.HexColor("#3730a3")),
    "MISSING_OLD_FILE": (colors.HexColor("#e0e7ff"), colors.HexColor("#3730a3")),
    "UNREADABLE":       (colors.HexColor("#fecaca"), colors.HexColor("#7f1d1d")),
    "MISSING_BOTH":     (colors.HexColor("#fecaca"), colors.HexColor("#7f1d1d")),
}


def to_dataframe(results: List[dict]) -> pd.DataFrame:
    """Convert list of result dicts to a nicely labelled DataFrame."""
    df = pd.DataFrame(results, columns=_COLUMNS)
    df = df.rename(columns=_DISPLAY_COLUMNS)
    return df


def _safe(text: str) -> str:
    """Strip characters outside Latin-1 (ReportLab standard fonts limitation)."""
    return str(text).encode("latin-1", errors="ignore").decode("latin-1")


def to_pdf(results: List[dict]) -> bytes:
    """
    Generate a styled PDF report using reportlab.
    Returns in-memory bytes of the PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Bulk PDF Comparison Report",
        author="Aditya",
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Title ─────────────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#1e1b4b"),
        spaceAfter=4,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    )
    sub_style = ParagraphStyle(
        "ReportSub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        spaceAfter=2,
    )
    accent_style = ParagraphStyle(
        "ReportAccent",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6d28d9"),
        spaceAfter=2,
        fontName="Helvetica-Bold",
    )

    story.append(Paragraph("Bulk PDF Comparison Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}", sub_style))
    story.append(Paragraph("Made by Aditya", accent_style))
    story.append(HRFlowable(
        width="100%", thickness=1.5,
        color=colors.HexColor("#6d28d9"), spaceAfter=10,
    ))

    # ── Summary stats ─────────────────────────────────────────────────────────
    statuses  = [r["status"] for r in results]
    n_total   = len(results)
    n_same    = statuses.count("SAME")
    n_changed = statuses.count("CHANGED")
    n_missing = sum(1 for s in statuses if "MISSING" in s)
    n_unread  = sum(1 for s in statuses if "UNREAD" in s or s == "MISSING_BOTH")

    summary_data = [
        ["Total Pairs", "Same", "Changed", "Missing", "Unreadable"],
        [str(n_total),  str(n_same), str(n_changed), str(n_missing), str(n_unread)],
    ]
    summary_table = Table(summary_data, colWidths=[5 * cm] * 5)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  9),
        ("BACKGROUND",    (0, 1), (-1, 1),  colors.HexColor("#f1f5f9")),
        ("FONTNAME",      (0, 1), (-1, 1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 1), (-1, 1),  14),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        # stat row individual cell colors
        ("TEXTCOLOR",     (0, 1), (0, 1),  colors.HexColor("#1e3a8a")),  # total — blue
        ("TEXTCOLOR",     (1, 1), (1, 1),  colors.HexColor("#065f46")),  # same  — green
        ("TEXTCOLOR",     (2, 1), (2, 1),  colors.HexColor("#7c2d12")),  # changed — orange
        ("TEXTCOLOR",     (3, 1), (3, 1),  colors.HexColor("#3730a3")),  # missing — indigo
        ("TEXTCOLOR",     (4, 1), (4, 1),  colors.HexColor("#7f1d1d")),  # unread  — red
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Results table ─────────────────────────────────────────────────────────
    header = [
        "Identifier", "Old File", "New File",
        "Old\nPages", "New\nPages", "Similarity", "Status", "Notes",
    ]
    col_widths = [2.2*cm, 5.8*cm, 5.8*cm, 1.6*cm, 1.6*cm, 2.2*cm, 3.6*cm, 4.6*cm]

    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
        wordWrap="CJK",
    )
    hdr_style = ParagraphStyle(
        "Hdr",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        leading=10,
    )

    table_data = [[Paragraph(h, hdr_style) for h in header]]

    for r in results:
        sim = r["similarity"]
        sim_str = f"{sim:.4f}" if isinstance(sim, float) else _safe(str(sim))
        row = [
            Paragraph(_safe(r["identifier"]), cell_style),
            Paragraph(_safe(r["old_file"]),   cell_style),
            Paragraph(_safe(r["new_file"]),   cell_style),
            Paragraph(_safe(str(r["old_pages"])), cell_style),
            Paragraph(_safe(str(r["new_pages"])), cell_style),
            Paragraph(sim_str,                    cell_style),
            Paragraph(_safe(r["status"]),         cell_style),
            Paragraph(_safe(str(r.get("notes", "") or "")), cell_style),
        ]
        table_data.append(row)

    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    ts = TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, colors.HexColor("#6d28d9")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        # Alternating row backgrounds
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [colors.HexColor("#f8fafc"), colors.HexColor("#f1f5f9")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
    ])

    # Per-row: color-code the Status cell (column 6)
    for i, r in enumerate(results, start=1):
        status = r.get("status", "")
        if status in _STATUS_COLORS:
            bg, fg = _STATUS_COLORS[status]
            ts.add("BACKGROUND", (6, i), (6, i), bg)
            ts.add("TEXTCOLOR",  (6, i), (6, i), fg)
            ts.add("FONTNAME",   (6, i), (6, i), "Helvetica-Bold")

    results_table.setStyle(ts)
    story.append(results_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

