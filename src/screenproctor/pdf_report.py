"""Self-contained local PDF reports. No network resources or model inference."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape


def pdf_report_bytes(report, directory):
    """Embed validated local evidence, reporting missing images explicitly."""
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from .review import (
        REPORT_VERSION,
        SCREEN_INTERPRETATION,
        VALIDATION_NOTE,
        coverage_summary,
        evidence_path,
        grouped_incidents,
        screen_change_summary,
    )

    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, filename in [
        ("ReportVera", "Vera.ttf"),
        ("ReportVeraBold", "VeraBd.ttf"),
    ]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    pdfmetrics.registerFontFamily(
        "ReportVera", normal="ReportVera", bold="ReportVeraBold"
    )
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "ReportVera"
    styles["Title"].fontName = styles["Heading1"].fontName = styles[
        "Heading2"
    ].fontName = "ReportVeraBold"
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 15
    styles.add(
        ParagraphStyle(
            "Caption",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
        )
    )
    styles.add(
        ParagraphStyle(
            "EvidenceTitle",
            parent=styles["Caption"],
            alignment=TA_CENTER,
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=44,
        bottomMargin=44,
        title="ScreenProctor video review",
        author="ScreenProctor POC",
    )
    story = []

    def paragraph(text, style="BodyText"):
        return Paragraph(escape(str(text)), styles[style])

    def add(text, style="BodyText"):
        story.append(paragraph(text, style))

    def table(rows, widths):
        value = Table(
            [[paragraph(cell, "Caption") for cell in row] for row in rows],
            colWidths=widths,
            repeatRows=1,
            hAlign="LEFT",
        )
        value.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(value)

    def picture(relative, caption, max_height):
        add(caption, "EvidenceTitle")
        path = evidence_path(directory, relative)
        if path is None:
            add(
                "Screenshot unavailable: original evidence file was not supplied or is outside the report evidence directory.",
                "Caption",
            )
            return
        try:
            # Force decoding here so corrupt files get a readable placeholder.
            from PIL import Image as PILImage

            with PILImage.open(path) as source:
                source.load()
            item = Image(str(path))
            scale = min(document.width / item.imageWidth, max_height / item.imageHeight)
            item.drawWidth = item.imageWidth * scale
            item.drawHeight = item.imageHeight * scale
            story.append(item)
        except (OSError, ValueError):
            add(
                "Screenshot unavailable: evidence image could not be decoded.",
                "Caption",
            )

    incidents = grouped_incidents(report)
    summary = screen_change_summary(report)
    coverage = coverage_summary(report)
    add("Video review report", "Title")
    add(f"Source: {report.get('source_video', 'Unspecified video')}")
    add(
        f"Analysis engine: {report.get('analysis_version', 'unknown')}  |  Report format: {REPORT_VERSION}",
        "Caption",
    )
    add(
        f"Recording type: {report.get('mode', 'unspecified')}  |  Last analyzed sample: {report.get('last_sample_seconds', 'unknown')} s",
        "Caption",
    )
    add("Findings", "Heading1")
    add(summary["message"])
    add(
        f"{len(incidents)} grouped observations from {len(report.get('events', []))} raw records. Related phone-placement and possible-use labels count as one incident."
    )
    add(SCREEN_INTERPRETATION)
    story.append(Spacer(1, 12))
    if incidents:
        table(
            [["Time in video (seconds)", "Observation"]]
            + [
                [
                    f"{item['start_seconds']:.3f}–{item['end_seconds']:.3f}",
                    item["title"],
                ]
                for item in incidents
            ],
            [145, document.width - 145],
        )
    else:
        add(
            "No events met the configured evidence thresholds. This does not establish absence; check coverage."
        )
    add("Timing", "Heading2")
    add(
        "Screen-change times use the estimated transition window where available. Confirmation follows once the changed view is stable. Other event intervals are sampled observations, not exact physical onset or offset."
    )
    add("Review status", "Heading2")
    add(
        "Observations require human review and do not establish misconduct or active assistance."
    )
    add(VALIDATION_NOTE)

    story.append(PageBreak())
    add("Coverage and unassessed intervals", "Heading1")
    table(
        [["Capability", "Result", "Coverage"]]
        + [
            [
                item["capability"],
                item["result"],
                f"{item['coverage_percent']:g}%"
                if item["coverage_percent"] is not None
                else "Unknown",
            ]
            for item in coverage["capabilities"]
        ],
        [145, document.width - 210, 65],
    )
    story.append(Spacer(1, 10))
    add(coverage["note"])
    add("Screen intervals that could not be assessed", "Heading2")
    if coverage["unassessed_screen_intervals"]:
        for gap in coverage["unassessed_screen_intervals"]:
            end = (
                f"{gap['end_seconds']:.3f} s"
                if gap["end_seconds"] is not None
                else "end unknown"
            )
            add(
                f"{gap['start_seconds']:.3f} s – {end}: screen unassessed. {gap['reason']}"
            )
        add("Do not interpret these intervals as having no screen changes.")
    else:
        add(
            "No screen-localization gaps recorded. Check the capability result above: absent gap records alone do not establish full coverage."
        )
    add("Application identification", "Heading2")
    add(
        "Screen changes are reported independently of AI identification. If text is unreadable, an unidentified application still permits a visual-change alert."
    )
    add("Validation needed before general use", "Heading2")
    add(
        "Evaluate held-out videos across recording modes, lighting, resolutions, camera motion and device layouts. Annotate event intervals and unavailable periods. Measure event precision, recall, false alerts per hour, coverage and processing time. Split by participant/session and report visual changes separately from verified application transitions. See VALIDATION_PLAN.md."
    )
    add("Evidence", "Heading2")
    add(
        "Images below are embedded in this PDF. They show the original recorded content and should be handled as session data. Missing or unreadable evidence is explicitly marked."
    )

    for number, incident in enumerate(incidents, start=1):
        story.append(PageBreak())
        add(f"Observation {number}: {incident['title']}", "Heading1")
        add(
            f"{incident['start_seconds']:.3f}–{incident['end_seconds']:.3f} s",
            "Heading2",
        )
        if "confirmed_at_seconds" in incident:
            add(
                f"Timing: {incident['timing_basis'].replace('_', ' ')}. Confirmed at {incident['confirmed_at_seconds']:.3f} s.",
                "Caption",
            )
        add(incident["interpretation"] or incident["reason"])
        if len(incident["labels"]) > 1:
            add(
                "One incident with related phone-placement and possible-use labels; active operation remains unverified."
            )
        if incident["type"] == "screen_content_changed":
            for phase in ("before", "after"):
                stamp = incident.get(f"{phase}_timestamp_seconds")
                caption = f"{phase.capitalize()} the screen change"
                if stamp is not None:
                    caption += f" — recorded at {stamp:.3f} s"
                picture(incident.get(f"{phase}_screenshot"), caption, 240)
        elif "screenshot" in incident:
            stamp = incident.get("evidence_timestamp_seconds")
            caption = (
                f"Evidence at {stamp:.3f} s"
                if stamp is not None
                else "Recorded evidence"
            )
            picture(incident["screenshot"], caption, 350)
        else:
            add("No screenshot was recorded for this observation.", "Caption")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("ReportVera", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(48, 24, "ScreenProctor POC | Evidence for human review")
        canvas.drawRightString(A4[0] - 48, 24, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def write_report_pdf(report, directory, output=None):
    path = Path(output) if output is not None else Path(directory) / "report.pdf"
    data = pdf_report_bytes(report, directory)
    # Preserve existing exports rather than silently overwrite them.
    with path.open("xb") as target:
        target.write(data)
    return path
