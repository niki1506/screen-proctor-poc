import json
from fractions import Fraction

import av
import cv2
import numpy as np
import pytest

from screenproctor.analyzer import Config, analyze, shot_changed
from screenproctor.video import crop, frames
from screenproctor.vision import Object


def make_video(path, variable=False):
    rng = np.random.default_rng(42)
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=4)
        stream.width = 320
        stream.height = 240
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 4)
        for n in range(12):
            image = rng.integers(20, 220, (240, 320, 3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts = n + (3 if variable and n >= 5 else 0)
            frame.time_base = Fraction(1, 4)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


def test_variable_frame_timestamps_are_preserved(tmp_path):
    path = tmp_path / "vfr.mp4"
    make_video(path, variable=True)
    times = [t for t, _ in frames(path, 4)]
    assert len(times) == 12
    assert abs(times[5] - times[4] - 1) < 0.01


def test_invalid_crop_is_rejected():
    with pytest.raises(ValueError):
        crop(np.zeros((100, 100, 3), np.uint8), [0.8, 0, 0.5, 1])


def test_combined_requires_separate_calibrated_regions():
    with pytest.raises(ValueError):
        Config(mode="combined").validate()
    with pytest.raises(ValueError):
        Config(
            mode="combined", camera_roi=[0, 0, 0.5, 1], screen_roi=[0.4, 0, 0.6, 1]
        ).validate()


class TwoPeople:
    def predict(self, image):
        return [
            Object("person", (5, 5, 100, 220), 0.9, {"left_wrist": (50, 160)}),
            Object("person", (150, 5, 280, 220), 0.85, {"left_wrist": (200, 160)}),
            Object("phone", (220, 200, 250, 220), 0.8),
        ]


def test_video_to_report_with_people_and_phone_evidence(tmp_path):
    path = tmp_path / "input.mp4"
    make_video(path)
    output = tmp_path / "result"
    report = analyze(path, output, tmp_path, Config(), detector=TwoPeople())
    assert report["status"] == "success"
    assert (output / "review.html").is_file()
    assert (output / "report.pdf").read_bytes().startswith(b"%PDF-")
    assert "incident_summary" in report and "coverage_summary" in report
    assert "screen_change_summary" in report
    kinds = {event["type"] for event in report["events"]}
    assert "additional_person_candidate" in kinds and "phone_present" in kinds
    assert "possible_phone_use" not in kinds
    assert report["assessments"]["screen_changes"]["result"] == "not_assessable"
    assert all((output / e["screenshot"]).is_file() for e in report["events"])
    assert json.loads((output / "report.json").read_text())["status"] == "success"


def test_existing_output_is_preserved(tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    (output / "important.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        analyze(
            tmp_path / "missing.mp4", output, tmp_path, Config(), detector=TwoPeople()
        )
    assert (output / "important.txt").read_text() == "keep"


def test_decode_failure_writes_error_report(tmp_path):
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"broken")
    output = tmp_path / "result"
    with pytest.raises(av.error.InvalidDataError):
        analyze(source, output, tmp_path, Config(mode="screen"))
    assert json.loads((output / "report.json").read_text())["status"] == "error"


def test_telemetry_timestamp_validation(tmp_path):
    source = tmp_path / "input.mp4"
    make_video(source)
    telemetry = tmp_path / "telemetry.json"
    telemetry.write_text(json.dumps([{"time_seconds": 100, "type": "page_hidden"}]))
    with pytest.raises(ValueError, match="outside"):
        analyze(
            source,
            tmp_path / "result",
            tmp_path,
            Config(mode="screen"),
            telemetry=telemetry,
        )


def test_model_failure_writes_error_report(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise ValueError("Models missing")

    monkeypatch.setattr("screenproctor.analyzer.Detector", missing)
    with pytest.raises(ValueError, match="Models missing"):
        analyze(tmp_path / "input.mp4", tmp_path / "result", tmp_path, Config())
    assert (
        json.loads((tmp_path / "result" / "report.json").read_text())["status"]
        == "error"
    )


def test_ignore_region_is_actually_masked(tmp_path):
    source = tmp_path / "input.mp4"
    make_video(source)

    class CheckMask:
        def predict(self, image):
            assert not image[0:120, 0:160].any()
            return []

    report = analyze(
        source,
        tmp_path / "result",
        tmp_path,
        Config(ignore_regions=[[0, 0, 0.5, 0.5]]),
        detector=CheckMask(),
    )
    assert not report["events"]


def test_structural_cut_with_similar_color_distribution():
    image = np.zeros((100, 160, 3), np.uint8)
    image[:, :80] = 255
    other = np.zeros_like(image)
    other[:, 80:] = 255
    assert shot_changed(
        cv2.cvtColor(image, cv2.COLOR_BGR2HSV), cv2.cvtColor(other, cv2.COLOR_BGR2HSV)
    )


def test_time_range_preserves_source_timestamps(tmp_path):
    source = tmp_path / "input.mp4"
    make_video(source)
    report = analyze(
        source,
        tmp_path / "result",
        tmp_path,
        Config(start_seconds=1, end_seconds=2),
        detector=TwoPeople(),
    )
    assert report["sample_count"] == 5
    assert all(
        event["start_seconds"] >= 1 and event["end_seconds"] <= 2
        for event in report["events"]
    )


def test_fully_excluded_camera_is_not_assessable(tmp_path):
    source = tmp_path / "input.mp4"
    make_video(source)

    class NoInference:
        def predict(self, image):
            raise AssertionError("Fully excluded camera must not be analyzed")

    report = analyze(
        source,
        tmp_path / "result",
        tmp_path,
        Config(ignore_regions=[[0, 0, 1, 1]]),
        detector=NoInference(),
    )
    assert report["assessments"]["additional_person"]["result"] == "not_assessable"


def test_external_mode_attempts_screen_analysis_without_manual_corners(
    tmp_path, monkeypatch
):
    source = tmp_path / "input.mp4"
    make_video(source)

    class Located:
        def update(self, image, laptops):
            return (
                [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
                0.9,
                "test_localizer",
            )

    monkeypatch.setattr("screenproctor.analyzer.DisplayTracker", Located)
    report = analyze(
        source, tmp_path / "result", tmp_path, Config(), detector=TwoPeople()
    )
    assert report["screen_localization"]["usable_samples"] > 0
    assert (tmp_path / "result" / report["screen_localization"]["preview"]).is_file()


def test_periodic_ai_on_static_screen_without_transition(tmp_path, monkeypatch):
    image = np.full((240, 320, 3), 200, np.uint8)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, image.copy()) for n in range(16)),
    )

    class Scanner:
        calls = 0

        def scan(self, view):
            self.calls += 1
            return {
                "readable": True,
                "match": "ChatGPT",
                "score": 0.9,
                "matched_cues": ["ChatGPT", "message"],
                "identity_basis": "test",
            }

    scanner = Scanner()
    report = analyze(
        tmp_path / "static.mp4",
        tmp_path / "result",
        tmp_path,
        Config(mode="screen"),
        scanner=scanner,
    )
    ai = [e for e in report["events"] if e["type"] == "ai_interface_visible"]
    assert scanner.calls == 4 and len(ai) == 1
    assert (tmp_path / "result" / report["ai_inspection"]["latest_preview"]).is_file()
    assert report["ai_inspection"]["independent_of_screen_changes"] is True
    assert ai[0]["start_seconds"] == 0 and ai[0]["end_seconds"] == 3
    assert ai[0]["observed_support_seconds"] == 3
    assert not any(e["type"] == "screen_content_changed" for e in report["events"])
    assert (tmp_path / "result" / ai[0]["screenshot"]).is_file()


def test_ai_whole_laptop_independent_of_display_localization(tmp_path, monkeypatch):
    rng = np.random.default_rng(1)
    image = rng.integers(30, 220, (240, 320, 3), dtype=np.uint8)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, image.copy()) for n in range(12)),
    )

    class Laptop:
        def predict(self, image):
            return [Object("laptop", (30, 40, 300, 220), 0.9)]

    class Scanner:
        def scan(self, view):
            assert view.shape == (180, 270, 3)
            return {
                "readable": True,
                "match": "Claude",
                "score": 0.9,
                "matched_cues": ["Claude", "message"],
                "identity_basis": "test",
            }

    report = analyze(
        tmp_path / "video",
        tmp_path / "result",
        tmp_path,
        Config(auto_screen=False),
        detector=Laptop(),
        scanner=Scanner(),
    )
    assert report["assessments"]["screen_changes"]["result"] == "not_assessable"
    assert report["assessments"]["ai_interface"]["result"] == "candidate_detected"
    assert report["events"][0]["evidence_region"] == "whole_laptop_in_camera_crop"


def test_placement_generates_use_risk_without_wrist(tmp_path, monkeypatch):
    rng = np.random.default_rng(1)
    image = rng.integers(180, 220, (600, 800, 3), dtype=np.uint8)
    cv2.rectangle(image, (230, 160), (320, 370), (40, 40, 40), -1)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, image.copy()) for n in range(12)),
    )

    class Laptop:
        def predict(self, image):
            return [Object("laptop", (100, 100, 700, 550), 0.9)]

    report = analyze(
        tmp_path / "video",
        tmp_path / "result",
        tmp_path,
        Config(auto_screen=False, ai_scan=False),
        detector=Laptop(),
    )
    kinds = {e["type"] for e in report["events"]}
    assert {"phone_placement_candidate", "possible_phone_use"} <= kinds
    assert "possible_phone_interaction" not in kinds
    assert report["assessments"]["phone_use_risk"]["result"] == "candidate_detected"
    assert report["assessments"]["phone_interaction"]["result"] == "not_assessable"


def test_ocr_failure_and_disabled_are_not_assessable(tmp_path, monkeypatch):
    image = np.full((240, 320, 3), 200, np.uint8)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, image.copy()) for n in range(12)),
    )

    class Broken:
        def scan(self, view):
            raise RuntimeError("unavailable")

    for enabled in [True, False]:
        report = analyze(
            tmp_path / "video",
            tmp_path / str(enabled),
            tmp_path,
            Config(mode="screen", ai_scan=enabled),
            scanner=Broken(),
        )
        assert report["status"] == "success"
        assert report["assessments"]["ai_interface"]["result"] == "not_assessable"
        assert not report["events"]


def test_ai_inspection_preview_prefers_largest_laptop(tmp_path, monkeypatch):
    rng = np.random.default_rng(7)
    image = rng.integers(30, 220, (240, 320, 3), dtype=np.uint8)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, image.copy()) for n in range(8)),
    )

    class Laptops:
        def predict(self, image):
            return [
                Object("laptop", (10, 10, 50, 40), 0.9),
                Object("laptop", (60, 40, 300, 220), 0.9),
            ]

    class Scanner:
        calls = 0

        def scan(self, view):
            self.calls += 1
            return {"readable": False, "match": None}

    scanner = Scanner()
    report = analyze(
        tmp_path / "video",
        tmp_path / "result",
        tmp_path,
        Config(auto_screen=False),
        detector=Laptops(),
        scanner=scanner,
    )
    assert scanner.calls == 4
    assert report["ai_inspection"]["latest_region_box"] == [60, 40, 300, 220]
    assert report["ai_inspection"]["regions_scanned"] == 4


def test_screen_change_after_tracking_gap_has_before_after_evidence(
    tmp_path, monkeypatch
):
    rng = np.random.default_rng(8)
    base = rng.integers(70, 140, (400, 600, 3), dtype=np.uint8)
    base[80:300, 100:500] = 230
    for y in range(110, 290, 25):
        cv2.putText(
            base,
            "Document content",
            (120, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (40, 40, 40),
            1,
        )
    changed = base.copy()
    changed[80:300, 100:280] = 30
    images = [base.copy() if n < 4 else changed.copy() for n in range(14)]
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, im) for n, im in enumerate(images)),
    )
    corners = [
        [100 / 599, 80 / 399],
        [500 / 599, 80 / 399],
        [500 / 599, 300 / 399],
        [100 / 599, 300 / 399],
    ]

    class Locator:
        n = 0

        def update(self, *args):
            n = self.n
            self.n += 1
            return None if 4 <= n < 8 else (corners, 0.9, "test_boundary")

    class Laptop:
        def predict(self, image):
            return [Object("laptop", (90, 70, 510, 360), 0.9)]

    monkeypatch.setattr("screenproctor.analyzer.DisplayTracker", Locator)
    report = analyze(
        tmp_path / "video",
        tmp_path / "result",
        tmp_path,
        Config(minimum=0.5, phone_placement=False, ai_scan=False),
        detector=Laptop(),
    )
    changes = [e for e in report["events"] if e["type"] == "screen_content_changed"]
    assert len(changes) == 1
    event = changes[0]
    assert event["comparison_gap"]["resumed_seconds"] == 2
    assert event["application_identity"] == "unidentified"
    assert (tmp_path / "result" / event["before_screenshot"]).is_file()
    assert (tmp_path / "result" / event["after_screenshot"]).is_file()
    assert (
        report["screen_localization"]["tracking_gaps"][0]["first_missing_seconds"] == 1
    )


def test_ai_recognition_is_linked_to_screen_change_without_claiming_destination(
    tmp_path, monkeypatch
):
    before = np.full((240, 320, 3), 210, np.uint8)
    for y in range(30, 220, 25):
        cv2.putText(
            before,
            "Static chat interface",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (30, 30, 30),
            1,
        )
    after = before.copy()
    after[:, :140] = 30
    images = [before.copy() if n < 4 else after.copy() for n in range(16)]
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, im) for n, im in enumerate(images)),
    )

    class Scanner:
        def scan(self, view):
            return {
                "readable": True,
                "match": "ChatGPT",
                "score": 0.9,
                "matched_cues": ["ChatGPT", "message"],
                "identity_basis": "test",
            }

    report = analyze(
        tmp_path / "video",
        tmp_path / "result",
        tmp_path,
        Config(mode="screen", minimum=0.5),
        scanner=Scanner(),
    )
    change = next(e for e in report["events"] if e["type"] == "screen_content_changed")
    assert change["ai_interface_check"]["result"] == "candidate_detected"
    assert change["ai_interface_check"]["services"] == ["ChatGPT"]
    assert change["application_identity"] == "unidentified"


def test_screen_before_evidence_is_latest_unchanged_frame_with_capture_times(
    tmp_path, monkeypatch
):
    base = np.full((240, 320, 3), 200, np.uint8)
    # Stable texture allows meaningful image-quality checks.
    for y in range(20, 220, 20):
        cv2.putText(
            base,
            "Screen content",
            (8, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (50, 50, 50),
            1,
        )
    images = []
    for n in range(12):
        frame = base.copy()
        if n < 4:
            # A small changing cursor marker should refresh the before image
            # without becoming a screen-change incident itself.
            frame[210:220, 10 + n * 8 : 16 + n * 8] = (0, 0, 250)
        else:
            frame[30:185, 140:300] = 20
        images.append(frame)
    monkeypatch.setattr(
        "screenproctor.analyzer.frames",
        lambda *a: ((n / 4, im) for n, im in enumerate(images)),
    )
    report = analyze(
        tmp_path / "input",
        tmp_path / "result",
        tmp_path,
        Config(mode="screen", minimum=0.5, ai_scan=False),
    )
    changes = [e for e in report["events"] if e["type"] == "screen_content_changed"]
    assert len(changes) == 1
    event = changes[0]
    assert event["before_timestamp_seconds"] == 0.75
    assert event["after_timestamp_seconds"] == event["confirmed_at_seconds"]
    actual = cv2.imread(str(tmp_path / "result" / event["before_screenshot"]))
    # JPEG evidence must match the last baseline better than the initial frame.
    error_latest = np.mean(np.abs(actual.astype(float) - images[3]))
    error_initial = np.mean(np.abs(actual.astype(float) - images[0]))
    assert error_latest < error_initial
    assert (
        report["screen_change_summary"]["changes"][0]["before_timestamp_seconds"]
        == 0.75
    )
