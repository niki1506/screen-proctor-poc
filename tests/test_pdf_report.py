from io import BytesIO

import cv2
import numpy as np
import pytest
from pypdf import PdfReader

from screenproctor.cli import main
from screenproctor.pdf_report import pdf_report_bytes, write_report_pdf


def fixture_report(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    # Distinct images ensure both evidence states are embedded.
    for index, name in enumerate(["before.png", "after.png", "phone.png"]):
        cv2.imwrite(
            str(evidence / name), np.full((180, 320, 3), 60 + index * 60, np.uint8)
        )
    placement = {
        "type": "phone_placement_candidate",
        "start_seconds": 20.505,
        "end_seconds": 24.258,
        "identity": "uncertain_phone_shaped_obstruction",
        "basis": "portrait_geometry",
        "bounding_box": [10, 20, 30, 50],
        "screenshot": "evidence/phone.png",
        "reason": "A portrait object is placed against the laptop; active use unverified.",
    }
    return {
        "analysis_version": "0.4.2",
        "status": "success",
        "source_video": "reference <clip>.mp4",
        "last_sample_seconds": 31.008,
        "events": [
            placement,
            {**placement, "type": "possible_phone_use"},
            {
                "type": "screen_content_changed",
                "start_seconds": 25.753,
                "end_seconds": 26.505,
                "change_window_start_seconds": 25.260,
                "change_window_end_seconds": 25.753,
                "possible_screen_switch": True,
                "application_identity": "unidentified",
                "before_screenshot": "evidence/before.png",
                "after_screenshot": "evidence/after.png",
                "before_timestamp_seconds": 25.26,
                "after_timestamp_seconds": 26.505,
            },
        ],
        "assessments": {
            "screen_changes": {
                "result": "candidate_detected",
                "assessable_sample_fraction": 0.84,
            },
            "ai_interface": {
                "result": "not_assessable",
                "assessable_sample_fraction": 0,
            },
        },
        "screen_localization": {
            "tracking_gaps": [{"first_missing_seconds": 0, "resumed_seconds": 5.003}]
        },
    }


def test_pdf_is_self_contained_readable_and_groups_derived_phone_labels(tmp_path):
    data = fixture_report(tmp_path)
    document = PdfReader(BytesIO(pdf_report_bytes(data, tmp_path)))
    text = "\n".join(page.extract_text() for page in document.pages)
    assert len(document.pages) == 4  # overview, coverage, two grouped observations
    assert "2 grouped observations from 3 raw records" in text
    assert "25.260–25.753" in text and "Confirmed at 26.505" in text
    assert "recorded at 25.260 s" in text and "recorded at 26.505 s" in text
    assert "0.000 s – 5.003 s: screen unassessed" in text
    assert "84%" in text and "Could not be assessed" in text
    assert "application switch unverified" in text
    assert "Accuracy on unseen videos has not been established" in text
    assert "reference <clip>.mp4" in text
    assert sum(len(page.images) for page in document.pages) == 3
    assert "Observation 3:" not in text


def test_pdf_marks_missing_corrupt_and_unsafe_images_without_reading_outside(tmp_path):
    data = fixture_report(tmp_path)
    outside = tmp_path / "outside.png"
    cv2.imwrite(str(outside), np.full((20, 20, 3), 255, np.uint8))
    event = data["events"][-1]
    event["before_screenshot"] = "../outside.png"
    (tmp_path / "evidence" / "after.png").write_bytes(b"corrupt")
    # A symlink to an outside image must also be rejected.
    (tmp_path / "evidence" / "unsafe.png").symlink_to(outside)
    for event in data["events"][:2]:
        event["screenshot"] = "evidence/unsafe.png"
    document = PdfReader(BytesIO(pdf_report_bytes(data, tmp_path)))
    text = "\n".join(page.extract_text() for page in document.pages)
    assert "Screenshot unavailable" in text
    assert "could not be decoded" in text
    assert sum(len(page.images) for page in document.pages) == 0


def test_export_existing_report_preserves_files_and_observation_times(tmp_path):
    import json

    report = fixture_report(tmp_path)
    path = tmp_path / "report.json"
    original = json.dumps(report)
    path.write_text(original)
    output = tmp_path / "export.pdf"
    assert main(["export-pdf", "--report", str(path), "--output", str(output)]) == 0
    assert output.read_bytes().startswith(b"%PDF-")
    assert path.read_text() == original
    existing = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_report_pdf(report, tmp_path, output)
    assert output.read_bytes() == existing


def test_live_pdf_export_refreshes_cached_renderer(tmp_path, monkeypatch):
    from screenproctor import pdf_report, review

    def old_renderer(*args):
        raise RuntimeError("stale PDF renderer")

    monkeypatch.setattr(pdf_report, "pdf_report_bytes", old_renderer)
    data = review.pdf_report_bytes(fixture_report(tmp_path), tmp_path)
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
    assert "recorded at 25.260 s" in text
