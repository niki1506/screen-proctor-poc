import numpy as np
import cv2
import pytest

from screenproctor.screen import ScreenChanges, extract


def image(value):
    return np.full((200, 320, 3), value, np.uint8)


def test_unchanged_screen_does_not_report():
    detector = ScreenChanges()
    assert all(detector.update(t / 4, image(50)) is None for t in range(12))


def test_successive_views_do_not_need_return_to_initial_screen():
    detector = ScreenChanges(dwell=0.5)
    results = []
    for n, value in enumerate([0] * 4 + [100] * 5 + [220] * 5):
        event = detector.update(n / 4, image(value))
        if event:
            results.append(event)
    assert len(results) == 2
    assert all(event["type"] == "screen_content_changed" for event in results)


def test_brief_flash_is_suppressed():
    detector = ScreenChanges()
    assert all(
        detector.update(n / 4, image(v)) is None
        for n, v in enumerate([0, 0, 200, 0, 0, 0, 0])
    )


def test_perspective_extraction_and_invalid_corners():
    assert (
        extract(
            image(100), corners=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        ).shape[0]
        > 100
    )
    with pytest.raises(ValueError):
        extract(image(100), corners=[[0, 0], [1, 1], [1, 0], [0, 1]])


def test_white_to_white_interface_change_can_be_reported():
    detector = ScreenChanges(dwell=0.5)
    before = image(230)
    after = before.copy()
    after[20:75, 25:160] = 30
    results = []
    for n, frame in enumerate([before] * 4 + [after] * 6):
        result = detector.update(n / 4, frame)
        if result:
            results.append(result)
    assert len(results) == 1


def test_small_camera_translation_is_registered_before_comparison():
    before = image(180)
    for row in range(8):
        cv2.putText(
            before,
            "Stable display content",
            (5, 20 + row * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (40, 40, 40),
            1,
        )
    after = cv2.warpAffine(
        before,
        np.float32([[1, 0, 3], [0, 1, 2]]),
        (320, 200),
        borderMode=cv2.BORDER_REFLECT,
    )
    assert ScreenChanges.distance(before, after) < 0.03


def test_exposure_change_alone_is_not_a_screen_transition():
    before = image(100)
    after = image(135)
    assert ScreenChanges.distance(before, after) == 0


def test_changed_view_survives_short_tracking_gap_without_counting_gap_as_support():
    detector = ScreenChanges(dwell=0.5)
    for t in [0, 0.25, 0.5, 0.75]:
        assert detector.update(t, image(50)) is None
    detector.missing(1)
    detector.missing(1.25)
    assert detector.update(2, image(200)) is None
    assert detector.update(2.25, image(200)) is None
    event = detector.update(2.5, image(200))
    assert event["type"] == "screen_content_changed"
    assert event["label"] == "Screen change"
    assert event["confirmed_at_seconds"] == 2.5
    assert event["start_seconds"] == 2
    assert event["comparison_gap"] == {
        "last_usable_seconds": 0.75,
        "resumed_seconds": 2,
    }
    assert event["onset_is_uncertain"] is True
    assert event["application_identity"] == "unidentified"


def test_unchanged_view_after_gap_does_not_report_switch():
    detector = ScreenChanges(dwell=0.5)
    for t in [0, 0.25, 0.5]:
        detector.update(t, image(50))
    detector.missing(0.75)
    assert all(detector.update(t, image(50)) is None for t in [2, 2.25, 2.5, 2.75])


def test_long_gap_reports_unassessed_reset_instead_of_switch():
    detector = ScreenChanges(dwell=0.5)
    detector.update(0, image(50))
    detector.update(0.25, image(50))
    detector.missing(0.5)
    event = detector.update(7, image(200))
    assert event["type"] == "screen_comparison_reset"
    assert event["reset_cause"] == "screen_gap_exceeded_comparison_limit"
    assert all(detector.update(t, image(200)) is None for t in [7.25, 7.5, 7.75])


def test_changed_crop_is_not_a_content_change():
    detector = ScreenChanges(dwell=0.5)
    detector.update(0, image(50))
    event = detector.update(0.25, image(200), comparable=False)
    assert event["type"] == "screen_comparison_reset"
    assert event["reset_cause"] == "display_region_changed"


def low_contrast_page(dense):
    page = image(230)
    lines = range(22, 184, 9) if dense else [22, 180]
    for row in lines:
        cv2.putText(
            page,
            "Subject message recipient details",
            (8, row),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (208, 208, 208),
            1,
            cv2.LINE_AA,
        )
    return page


def test_low_contrast_text_layout_changes_with_same_background_are_detected():
    before, after = low_contrast_page(False), low_contrast_page(True)
    # No pixel has the former >30-level color difference, even before smoothing.
    assert np.max(np.abs(before.astype(float) - after)) < 30
    detector = ScreenChanges(dwell=0.75)
    events = []
    for n, frame in enumerate([before] * 4 + [after] * 4):
        event = detector.update(n / 4, frame)
        if event:
            events.append(event)
    assert len(events) == 1
    assert events[0]["change_window_start_seconds"] == 0.75
    assert events[0]["change_window_end_seconds"] == 1
    assert events[0]["confirmed_at_seconds"] == 1.75


def test_text_edges_do_not_turn_exposure_or_small_translation_into_changes():
    before = low_contrast_page(True)
    exposure = cv2.add(before, np.full_like(before, 15))
    moved = cv2.warpAffine(
        before,
        np.float32([[1, 0, 2], [0, 1, 1]]),
        (320, 200),
        borderMode=cv2.BORDER_REFLECT,
    )
    detector = ScreenChanges()
    sequence = [before] * 4 + [exposure] * 4 + [moved] * 4 + [before] * 4
    assert not any(detector.update(n / 4, frame) for n, frame in enumerate(sequence))


def test_slowly_changing_frames_cannot_accumulate_stable_candidate_support():
    detector = ScreenChanges(dwell=0.75)
    assert detector.update(0, image(0)) is None
    # Each adjacent step is below the motion threshold, but accumulated layout
    # drift from the candidate is large; it must settle before confirmation.
    for n in range(1, 10):
        frame = image(0)
        frame[: n * 20] = 200
        assert detector.update(n / 4, frame) is None
    assert detector.update(2.5, frame) is None
    assert detector.update(2.75, frame) is None
    event = detector.update(3, frame)
    assert event is not None and event["confirmed_at_seconds"] == 3
