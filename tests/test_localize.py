import cv2
import numpy as np
from screenproctor.localize import locate_screen, DisplayTracker
from screenproctor.vision import Object


def display_image():
    image = np.full((500, 800, 3), 80, np.uint8)
    cv2.rectangle(image, (180, 80), (650, 380), (230, 230, 230), -1)
    for row in range(8):
        cv2.putText(
            image,
            "Sample document content",
            (210, 115 + row * 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (25, 25, 25),
            1,
        )
    return image


def test_text_bearing_display_is_automatically_localized():
    image = display_image()
    result = locate_screen(image, [Object("laptop", (150, 60, 680, 460), 0.9)])
    assert result is not None
    points = np.array(result[0]) * [799, 499]
    assert abs(points[:, 0].min() - 180) < 10
    assert abs(points[:, 1].min() - 80) < 10


def test_plain_laptop_back_is_not_a_text_bearing_display():
    image = np.full((500, 800, 3), 80, np.uint8)
    cv2.rectangle(image, (180, 80), (650, 380), (20, 20, 20), -1)
    assert locate_screen(image, [Object("laptop", (150, 60, 680, 460), 0.9)]) is None


def test_display_can_be_reacquired_after_camera_movement():
    image = display_image()
    tracker = DisplayTracker()
    assert (
        tracker.update(image, [Object("laptop", (150, 60, 680, 460), 0.9)]) is not None
    )
    shifted = cv2.warpAffine(image, np.float32([[1, 0, 4], [0, 1, 2]]), (800, 500))
    assert (
        tracker.update(shifted, [Object("laptop", (154, 62, 684, 462), 0.9)])
        is not None
    )


def test_split_dark_and_bright_panes_keep_full_display_boundary():
    image = display_image()
    cv2.rectangle(image, (181, 81), (400, 379), (25, 25, 25), -1)
    cv2.putText(
        image,
        "Chat panel",
        (210, 140),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (180, 180, 180),
        1,
    )
    found = locate_screen(image, [Object("laptop", (150, 60, 680, 460), 0.9)])
    assert found is not None
    points = np.array(found[0]) * [799, 499]
    assert points[:, 0].min() < 190 and points[:, 0].max() > 640


def test_reacquisition_rejects_smaller_application_pane(monkeypatch):
    from screenproctor.localize import compatible_regions

    full = [[0.2, 0.1], [0.8, 0.1], [0.8, 0.8], [0.2, 0.8]]
    pane = [[0.5, 0.1], [0.8, 0.1], [0.8, 0.8], [0.5, 0.8]]
    assert not compatible_regions(full, pane)
    tracker = DisplayTracker()
    tracker.reference = full
    monkeypatch.setattr("screenproctor.localize.physical_screen", lambda *a: None)
    monkeypatch.setattr("screenproctor.localize.text_region", lambda *a: (pane, 0.9))
    assert tracker.update(display_image(), []) is None


def test_normalized_polygon_overlap_is_stable_under_subpixel_jitter():
    from screenproctor.localize import polygon_iou, compatible_regions

    a = [[0.515, 0.519], [0.712, 0.577], [0.667, 0.853], [0.472, 0.740]]
    b = [
        [0.5152794718742371, 0.5191110372543335],
        [0.7117500305175781, 0.5771520733833313],
        [0.6670491695404053, 0.8527700901031494],
        [0.47257545590400696, 0.7400586009025574],
    ]
    assert polygon_iou(a, b) > 0.99
    assert compatible_regions(a, b)
