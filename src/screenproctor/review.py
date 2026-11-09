"""Readable review summaries derived from observations, without reclassification."""

from html import escape
from pathlib import Path


def screen_change_timing(event):
    """Use the estimated transition window, preserving the confirmation timestamp."""
    estimated = (
        "change_window_start_seconds" in event and "change_window_end_seconds" in event
    )
    return {
        "start_seconds": event["change_window_start_seconds"]
        if estimated
        else event["start_seconds"],
        "end_seconds": event["change_window_end_seconds"]
        if estimated
        else event["end_seconds"],
        "timing_basis": "estimated_change_window"
        if estimated
        else "observation_interval",
        "confirmed_at_seconds": event.get("confirmed_at_seconds", event["end_seconds"]),
    }


def screen_change_summary(report):
    changes = sorted(
        (
            e
            for e in report.get("events", [])
            if e.get("type") == "screen_content_changed"
        ),
        key=lambda event: event["start_seconds"],
    )
    items = [
        {
            "title": "Screen change",
            **screen_change_timing(event),
            "application_identity": event.get("application_identity", "unidentified"),
            "interpretation": SCREEN_INTERPRETATION,
            **{
                key: event[key]
                for key in (
                    "before_screenshot",
                    "after_screenshot",
                    "before_timestamp_seconds",
                    "after_timestamp_seconds",
                )
                if key in event
            },
        }
        for event in changes
    ]
    count = len(items)
    result = (
        "candidate_detected"
        if count
        else report.get("assessments", {})
        .get("screen_changes", {})
        .get("result", "not_assessable")
    )
    message = f"{count} screen change{'s' if count != 1 else ''} detected."
    if items:
        latest = items[-1]
        message += (
            f" Latest: {latest['start_seconds']:.3f}–{latest['end_seconds']:.3f}s."
        )
    if not count and result == "not_assessable":
        message = "Screen changes could not be assessed."
    return {
        "result": result,
        "event_count": count,
        "message": message,
        "changes": items,
        "note": "Screen-change times show the estimated transition window when available. Confirmation time is recorded separately.",
    }


def write_review_html(report, directory):
    """Write a local page with the latest screen comparison first."""
    directory = Path(directory).resolve()
    summary = screen_change_summary(report)
    cards = []
    for change in reversed(summary["changes"]):
        pictures = []
        for key, caption in [
            ("before_screenshot", "Before"),
            ("after_screenshot", "After"),
        ]:
            relative = change.get(key)
            if not isinstance(relative, str):
                continue
            target = (directory / relative).resolve()
            if (
                not target.is_relative_to(directory / "evidence")
                or not target.is_file()
            ):
                continue
            stamp = change.get(key.replace("screenshot", "timestamp_seconds"))
            if stamp is not None:
                caption += f" at {stamp:.3f}s"
            pictures.append(
                f'<figure><figcaption>{caption}</figcaption><img src="{escape(relative, quote=True)}" alt="{caption} screen view"></figure>'
            )
        cards.append(
            f'<section><h2>{change["start_seconds"]:.3f}–{change["end_seconds"]:.3f}s · Screen change</h2><p>Timing: {escape(change["timing_basis"].replace("_", " "))}. Confirmed at {change["confirmed_at_seconds"]:.3f}s.</p><div class="pictures">{"".join(pictures)}</div></section>'
        )
    other_cards = []
    for incident in grouped_incidents(report):
        if incident["type"] == "screen_content_changed":
            continue
        image = evidence_path(directory, incident.get("screenshot"))
        picture = (
            f'<img src="{escape(incident["screenshot"], quote=True)}" alt="Incident evidence">'
            if image
            else "<p>Screenshot unavailable.</p>"
        )
        other_cards.append(
            f"<section><h2>{incident['start_seconds']:.3f}–{incident['end_seconds']:.3f}s · {escape(incident['title'])}</h2>"
            f"<p>{escape(incident['reason'])}</p>"
            + (
                "<p>One incident with phone placement and possible-use labels.</p>"
                if len(incident["labels"]) > 1
                else ""
            )
            + picture
            + "</section>"
        )
    coverage = coverage_summary(report)
    gap_text = "".join(
        f"<li>{gap['start_seconds']:.3f}–{gap['end_seconds']:.3f}s: screen unassessed</li>"
        for gap in coverage["unassessed_screen_intervals"]
        if gap["end_seconds"] is not None
    )
    coverage_html = (
        "<section><h2>Coverage and interpretation</h2><ul>"
        + "".join(
            f"<li>{escape(item['capability'])}: {escape(item['result'])}; coverage {item['coverage_percent']}%</li>"
            for item in coverage["capabilities"]
        )
        + "</ul><ul>"
        + gap_text
        + "</ul><p>"
        + escape(coverage["note"])
        + "</p><p>"
        + escape(SCREEN_INTERPRETATION)
        + "</p><p>"
        + escape(VALIDATION_NOTE)
        + "</p></section>"
    )
    page = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ScreenProctor review</title>
<style>body{font:16px system-ui,sans-serif;background:#f4f6fa;color:#172033;max-width:1000px;margin:40px auto;padding:0 20px}header,section{background:white;border:1px solid #dbe2eb;border-radius:12px;padding:24px;margin:20px 0}h1{font-size:28px}h2{font-size:20px}.summary{font-size:22px;font-weight:650;color:#175136}.pictures{display:flex;gap:20px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:220px}img{width:100%;border:1px solid #dbe2eb}figcaption{font-weight:600;margin:8px 0}p{line-height:1.5}</style>
<header><h1>ScreenProctor review</h1><p class="summary">"""
        + escape(summary["message"])
        + "</p><p>"
        + escape(summary["note"])
        + "</p><p>Source: "
        + escape(str(report.get("source_video", "video")))
        + " · Analysis version: "
        + escape(str(report.get("analysis_version", "unknown")))
        + "</p></header>"
        + coverage_html
        + "".join(cards)
        + "".join(other_cards)
        + "</html>"
    )
    (directory / "review.html").write_text(page, encoding="utf8")


def review_report(report):
    """Refresh derived timing for exports without changing stored observations."""
    return {
        **report,
        "screen_change_summary": screen_change_summary(report),
        "incident_summary": {
            "incident_count": len(grouped_incidents(report)),
            "raw_observation_count": len(report.get("events", [])),
            "incidents": grouped_incidents(report),
            "note": "Matching phone placement and derived possible-use labels describe one incident. Raw observations are retained.",
        },
        "coverage_summary": coverage_summary(report),
        "review_metadata": {
            **report.get("review_metadata", {}),
            "presentation_version": REPORT_VERSION,
            "validation_status": "not_validated_on_unseen_sessions",
            "validation_note": VALIDATION_NOTE,
            "timestamp_note": "Screen summary and incident times use estimated transition windows where available. Raw screen-event start/end times retain stable-observation intervals; confirmed_at_seconds records confirmation.",
        },
    }


REPORT_VERSION = "0.4.4"
SCREEN_INTERPRETATION = (
    "Visual screen change; application switch unverified. Physical obstruction, "
    "notifications, scrolling or a changed layout may produce this alert."
)
VALIDATION_NOTE = (
    "Accuracy on unseen videos has not been established. Validate on separately "
    "annotated sessions before general use. Existing reference-video results provide regression evidence only."
)
TITLES = {
    "additional_person_candidate": "Additional person candidate",
    "phone_present": "Phone visible",
    "phone_placement_candidate": "Phone placement / possible use",
    "possible_phone_use": "Possible phone use",
    "possible_phone_interaction": "Possible phone interaction",
    "screen_content_changed": "Screen change",
    "screen_comparison_reset": "Screen comparison unavailable",
    "ai_interface_visible": "AI interface visible; active use unverified",
    "ai_interface_candidate": "Possible AI interface",
    "foreground_app_changed": "Recorded application change (telemetry; source unverified)",
    "page_hidden": "Page hidden (provided telemetry)",
    "window_blur": "Window lost focus (provided telemetry)",
    "fullscreen_exit": "Exited fullscreen (provided telemetry)",
}
CAPABILITIES = {
    "additional_person": "Additional people",
    "phone_presence": "Phone presence",
    "phone_interaction": "Phone interaction",
    "phone_use_risk": "Possible phone use",
    "screen_changes": "Visual screen changes",
    "ai_interface": "AI application identification",
}
RESULTS = {
    "candidate_detected": "Observation flagged for review",
    "no_event_observed": "No qualifying event observed",
    "not_assessable": "Could not be assessed",
}


def evidence_path(directory, relative):
    """Only allow existing images under this report's evidence directory."""
    if not isinstance(relative, str):
        return None
    directory = Path(directory).resolve()
    target = (directory / relative).resolve()
    if (
        not target.is_relative_to(directory / "evidence")
        or target.suffix.lower() not in {".jpg", ".jpeg", ".png"}
        or not target.is_file()
    ):
        return None
    return target


def grouped_incidents(report):
    """Group only an exact placement/derived-use pair; retain raw event indices."""
    events = report.get("events", [])
    consumed = set()
    incidents = []
    for index, event in enumerate(events):
        if index in consumed:
            continue
        members = [index]
        kind = event.get("type", "observation")
        if kind in {"phone_placement_candidate", "possible_phone_use"}:
            counterpart = (
                "possible_phone_use"
                if kind == "phone_placement_candidate"
                else "phone_placement_candidate"
            )
            # Time overlap alone is insufficient: two separate devices can coexist.
            identity_keys = (
                "start_seconds",
                "end_seconds",
                "identity",
                "basis",
                "bounding_box",
            )
            if all(key in event for key in identity_keys):
                for other_index, other in enumerate(events):
                    if (
                        other_index != index
                        and other_index not in consumed
                        and other.get("type") == counterpart
                        and all(event[key] == other.get(key) for key in identity_keys)
                    ):
                        members.append(other_index)
                        consumed.add(other_index)
                        break
        consumed.add(index)
        timing = (
            screen_change_timing(event)
            if kind == "screen_content_changed"
            else {
                "start_seconds": event["start_seconds"],
                "end_seconds": event["end_seconds"],
            }
        )
        title = (
            "Phone placement / possible use"
            if len(members) > 1
            else TITLES.get(kind, kind.replace("_", " ").capitalize())
        )
        incidents.append(
            {
                "title": title,
                "type": kind,
                **timing,
                "event_indices": sorted(members),
                "labels": sorted({events[i]["type"] for i in members}),
                "reason": event.get("reason", "Review the recorded evidence."),
                "interpretation": SCREEN_INTERPRETATION
                if kind == "screen_content_changed"
                else "",
                **{
                    key: event[key]
                    for key in (
                        "screenshot",
                        "before_screenshot",
                        "after_screenshot",
                        "evidence_timestamp_seconds",
                        "before_timestamp_seconds",
                        "after_timestamp_seconds",
                    )
                    if key in event
                },
            }
        )
    return sorted(incidents, key=lambda item: item["start_seconds"])


def coverage_summary(report):
    capabilities = []
    for key, assessment in report.get("assessments", {}).items():
        capabilities.append(
            {
                "capability": CAPABILITIES.get(key, key.replace("_", " ")),
                "result": RESULTS.get(assessment.get("result"), "Unknown"),
                "coverage_percent": round(
                    100 * assessment["assessable_sample_fraction"], 1
                )
                if "assessable_sample_fraction" in assessment
                else None,
            }
        )
    gaps = []
    for gap in report.get("screen_localization", {}).get("tracking_gaps", []):
        end = gap.get("resumed_seconds")
        gaps.append(
            {
                "start_seconds": gap["first_missing_seconds"],
                "end_seconds": end
                if end is not None
                else report.get("last_sample_seconds"),
                "resumed": end is not None,
                "reason": gap.get("reason", "Display unavailable."),
            }
        )
    return {
        "capabilities": capabilities,
        "unassessed_screen_intervals": gaps,
        "note": "Coverage measures usable samples, not detection accuracy. AI identification coverage measures readable scheduled scans. No event observed does not prove absence.",
    }


def pdf_report_bytes(report, directory):
    # Both helpers are stateless. A live Streamlit process can retain the old
    # PDF renderer even after reloading review.py, so refresh it on export too.
    from importlib import reload
    from . import pdf_report

    return reload(pdf_report).pdf_report_bytes(report, directory)
