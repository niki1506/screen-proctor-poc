from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_upload_ui_initializes():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "ScreenProctor"


def test_existing_v04_report_prominently_shows_change_despite_unknown_ai(tmp_path):
    import json
    import cv2
    import numpy as np

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in ["before.png", "after.png"]:
        cv2.imwrite(str(evidence / name), np.full((40, 60, 3), 120, np.uint8))
    report = {
        "analysis_version": "0.4.0",
        "mode": "external",
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
        "events": [
            {
                "type": "screen_content_changed",
                "change_window_start_seconds": 15.0,
                "change_window_end_seconds": 15.25,
                "start_seconds": 15.25,
                "end_seconds": 16.0,
                "application_identity": "unidentified",
                "before_screenshot": "evidence/before.png",
                "after_screenshot": "evidence/after.png",
            }
        ],
        "screen_localization": {
            "preview": "evidence/before.png",
            "location_preview": "evidence/before.png",
        },
        "diagnostics": {},
        "limitations": [],
    }
    placement = {
        "type": "phone_placement_candidate",
        "start_seconds": 20.5,
        "end_seconds": 24.25,
        "identity": "uncertain_phone_shaped_obstruction",
        "basis": "portrait_geometry",
        "bounding_box": [10, 20, 30, 50],
        "screenshot": "evidence/before.png",
    }
    report["events"].extend([placement, {**placement, "type": "possible_phone_use"}])
    report["screen_localization"]["tracking_gaps"] = [
        {"first_missing_seconds": 0, "resumed_seconds": 5.003}
    ]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    app.session_state["report_path"] = str(path)
    app.run(timeout=30)
    assert not app.exception
    assert any("1 screen change detected" in item.value for item in app.success)
    assert any("Screen changes detected" == item.value for item in app.subheader)
    assert any("15.000–15.250s · Screen change" == item.label for item in app.expander)
    latest = next(
        item for item in app.expander if item.label == "15.000–15.250s · Screen change"
    )
    assert latest.proto.expanded
    assert not any("earlier detector" in item.value for item in app.warning)
    assert any("Other observations (1)" == item.value for item in app.subheader)
    assert any("Screen unassessed: 0.000–5.003s" in item.value for item in app.warning)
    assert any("application switches" in item.value for item in app.caption)
    assert any(
        "Download PDF report with screenshots" == item.proto.label
        for item in app.get("download_button")
    )
    assert not app.error


def test_live_reload_recovers_a_cached_older_review_module(monkeypatch):
    from screenproctor import review

    # A live Streamlit process can retain the module from before these helpers existed.
    monkeypatch.delattr(review, "screen_change_timing")
    monkeypatch.delattr(review, "review_report")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    timing = review.screen_change_timing(
        {
            "start_seconds": 20.0,
            "end_seconds": 21.0,
            "change_window_start_seconds": 19.5,
            "change_window_end_seconds": 20.0,
        }
    )
    assert timing["start_seconds"] == 19.5 and timing["confirmed_at_seconds"] == 21.0
    assert callable(review.review_report)
