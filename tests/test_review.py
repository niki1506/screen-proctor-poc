from screenproctor.review import screen_change_summary, write_review_html


def report():
    return {
        "analysis_version": "0.4.0",
        "source_video": "input.mp4",
        "assessments": {
            "screen_changes": {"result": "candidate_detected"},
            "ai_interface": {"result": "not_assessable"},
        },
        "events": [
            {
                "type": "screen_content_changed",
                "start_seconds": 10.0,
                "end_seconds": 11.0,
                "application_identity": "unidentified",
                "before_screenshot": "evidence/a.png",
                "after_screenshot": "evidence/b.png",
            },
            {
                "type": "screen_comparison_reset",
                "start_seconds": 12.0,
                "end_seconds": 12.0,
            },
            {
                "type": "screen_content_changed",
                "start_seconds": 20.0,
                "end_seconds": 21.0,
                "application_identity": "unidentified",
                "before_screenshot": "evidence/a.png",
                "after_screenshot": "evidence/b.png",
            },
        ],
    }


def test_summary_counts_visual_changes_when_ai_identity_is_unknown():
    summary = screen_change_summary(report())
    assert summary["event_count"] == 2
    assert summary["result"] == "candidate_detected"
    assert "2 screen changes detected" in summary["message"]
    assert summary["changes"][-1]["start_seconds"] == 20
    assert summary["changes"][-1]["application_identity"] == "unidentified"


def test_unassessable_screen_is_not_reported_as_detected():
    data = {
        "events": [],
        "assessments": {"screen_changes": {"result": "not_assessable"}},
    }
    summary = screen_change_summary(data)
    assert summary["event_count"] == 0 and summary["result"] == "not_assessable"
    assert summary["message"] == "Screen changes could not be assessed."


def test_html_review_shows_latest_comparison_and_escapes_text(tmp_path):
    folder = tmp_path / "evidence"
    folder.mkdir()
    (folder / "a.png").write_bytes(b"fixture")
    (folder / "b.png").write_bytes(b"fixture")
    data = report()
    data["source_video"] = "<script>alert(1)</script>"
    write_review_html(data, tmp_path)
    html = (tmp_path / "review.html").read_text()
    assert html.index("20.000–21.000s") < html.index("10.000–11.000s")
    assert 'src="evidence/a.png"' in html and 'src="evidence/b.png"' in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    data["events"][0]["before_screenshot"] = "../outside.png"
    write_review_html(data, tmp_path)
    assert 'src="../outside.png"' not in (tmp_path / "review.html").read_text()


def test_estimated_change_window_is_primary_and_confirmation_is_separate(tmp_path):
    data = report()
    event = data["events"][-1]
    event["change_window_start_seconds"] = 19.5
    event["change_window_end_seconds"] = 20.0
    summary = screen_change_summary(data)
    latest = summary["changes"][-1]
    assert latest["start_seconds"] == 19.5 and latest["end_seconds"] == 20.0
    assert latest["confirmed_at_seconds"] == 21.0
    assert latest["timing_basis"] == "estimated_change_window"
    assert event["start_seconds"] == 20.0 and event["end_seconds"] == 21.0
    write_review_html(data, tmp_path)
    page = (tmp_path / "review.html").read_text()
    assert "19.500–20.000s · Screen change" in page
    assert "Confirmed at 21.000s" in page


def test_export_replaces_stale_summary_without_mutating_observations():
    from screenproctor.review import review_report

    data = report()
    data["events"][-1]["change_window_start_seconds"] = 19.5
    data["events"][-1]["change_window_end_seconds"] = 20.0
    data["screen_change_summary"] = {"message": "old timing"}
    exported = review_report(data)
    assert exported["screen_change_summary"]["changes"][-1]["start_seconds"] == 19.5
    assert exported["events"] == data["events"]
    assert data["screen_change_summary"] == {"message": "old timing"}


def test_grouped_phone_incident_preserves_events_and_separate_objects():
    from copy import deepcopy
    from screenproctor.review import review_report

    placement = {
        "type": "phone_placement_candidate",
        "start_seconds": 20.5,
        "end_seconds": 24.25,
        "identity": "uncertain_phone_shaped_obstruction",
        "basis": "portrait_geometry",
        "bounding_box": [10, 20, 30, 50],
    }
    use = {**placement, "type": "possible_phone_use"}
    separate = {**use, "bounding_box": [60, 20, 80, 50]}
    data = {"events": [use, placement, separate]}
    original = deepcopy(data)
    exported = review_report(data)
    grouped = exported["incident_summary"]
    assert grouped["incident_count"] == 2 and grouped["raw_observation_count"] == 3
    assert grouped["incidents"][0]["event_indices"] == [0, 1]
    assert grouped["incidents"][1]["event_indices"] == [2]
    assert data == original
    assert exported["events"] == original["events"]


def test_unrelated_possible_use_and_missing_identity_are_not_collapsed():
    from screenproctor.review import grouped_incidents

    placement = {
        "type": "phone_placement_candidate",
        "start_seconds": 1,
        "end_seconds": 3,
    }
    use = {**placement, "type": "possible_phone_use"}
    assert len(grouped_incidents({"events": [placement, use]})) == 2


def test_readable_coverage_retains_open_gaps_and_validation_status():
    from screenproctor.review import review_report

    data = {
        "events": [],
        "last_sample_seconds": 31,
        "assessments": {
            "screen_changes": {
                "result": "candidate_detected",
                "assessable_sample_fraction": 0.84,
            }
        },
        "screen_localization": {
            "tracking_gaps": [
                {"first_missing_seconds": 0, "resumed_seconds": 5.003},
                {"first_missing_seconds": 29, "resumed_seconds": None},
            ]
        },
    }
    result = review_report(data)
    coverage = result["coverage_summary"]
    assert coverage["capabilities"][0]["coverage_percent"] == 84
    assert coverage["unassessed_screen_intervals"][0]["end_seconds"] == 5.003
    assert coverage["unassessed_screen_intervals"][1]["end_seconds"] == 31
    assert not coverage["unassessed_screen_intervals"][1]["resumed"]
    assert (
        result["review_metadata"]["validation_status"]
        == "not_validated_on_unseen_sessions"
    )
