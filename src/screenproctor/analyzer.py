"""Offline orchestration, coverage, event evidence and optional recorded telemetry."""

import json
import math
import os
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np

from .events import Events
from .review import review_report, write_review_html
from .pdf_report import write_report_pdf
from .placement import phone_shaped_obstructions, positioned_phones
from .semantic import InterfaceScanner
from .screen import ScreenChanges, extract
from .localize import DisplayTracker, compatible_regions
from .video import crop, frames
from .vision import Detector, Object, Tracks, annotate, interaction, clear_person


@dataclass
class Config:
    mode: str = "external"
    fps: float = 4.0
    threshold: float = 0.35
    minimum: float = 0.75
    camera_roi: list | None = None
    screen_roi: list | None = None
    screen_corners: list | None = None
    ignore_regions: list | None = None
    start_seconds: float = 0.0
    end_seconds: float | None = None
    auto_screen: bool = True
    phone_placement: bool = True
    ai_scan: bool = True
    ai_interval: float = 1.0

    def validate(self):
        if not math.isfinite(self.ai_interval) or not 0.5 <= self.ai_interval <= 5:
            raise ValueError("AI scan interval must be between 0.5 and 5 seconds")
        if not isinstance(self.phone_placement, bool) or not isinstance(
            self.ai_scan, bool
        ):
            raise ValueError("Detection switches must be boolean")
        if self.mode not in {"external", "webcam", "screen", "combined"}:
            raise ValueError("Unknown recording mode")
        if not math.isfinite(self.fps) or not 0.25 <= self.fps <= 30:
            raise ValueError("FPS must be between 0.25 and 30")
        if not math.isfinite(self.threshold) or not 0 < self.threshold <= 1:
            raise ValueError("Detection threshold must be in (0,1]")
        if not math.isfinite(self.minimum) or self.minimum < 0.25:
            raise ValueError("Minimum event support must be at least 0.25 seconds")
        if not math.isfinite(self.start_seconds) or self.start_seconds < 0:
            raise ValueError("Start time must be a finite non-negative number")
        if self.end_seconds is not None and (
            not math.isfinite(self.end_seconds)
            or self.end_seconds <= self.start_seconds
        ):
            raise ValueError("End time must be after the start time")
        if self.mode == "combined" and (
            self.camera_roi is None or self.screen_roi is None
        ):
            raise ValueError("Combined recordings require camera and screen regions")
        for region in (self.camera_roi, self.screen_roi):
            if region is None:
                continue
            if len(region) != 4 or not all(math.isfinite(v) for v in region):
                raise ValueError("Regions need four finite normalized values")
            x, y, w, h = region
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
                raise ValueError("Regions must fit within the video")
        if self.mode == "combined":
            a, b = self.camera_roi, self.screen_roi
            if min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(
                a[1] + a[3], b[1] + b[3]
            ) > max(a[1], b[1]):
                raise ValueError(
                    "Combined camera and screen regions must not overlap; crop the screen to exclude the camera"
                )
        for region in self.ignore_regions or []:
            if len(region) != 4 or not all(math.isfinite(v) for v in region):
                raise ValueError("Ignore regions need four finite normalized values")
            x, y, w, h = region
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
                raise ValueError("Ignore regions must fit within the camera region")


def quality(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return (
        12 < float(gray.mean()) < 245
        and float(cv2.Laplacian(gray, cv2.CV_64F).var()) > 12
    )


def shot_changed(previous, image):
    if previous is None:
        return False
    a = cv2.calcHist([previous], [0, 1], None, [24, 24], [0, 180, 0, 256])
    b = cv2.calcHist([image], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(a, a)
    cv2.normalize(b, b)
    structural = float(np.mean(cv2.absdiff(previous[:, :, 2], image[:, :, 2]) > 50))
    return cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA) > 0.65 or structural > 0.5


def write_json(path, data):
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf8"
    ) as file:
        temporary = Path(file.name)
        try:
            json.dump(data, file, indent=2, allow_nan=False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def analyze(
    source,
    output,
    models,
    config,
    progress=None,
    telemetry=None,
    detector=None,
    scanner=None,
):
    config.validate()
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence"
    evidence.mkdir()
    counts = Counter()
    group = Events(config.minimum, max(0.6, 1.6 / config.fps))
    ai_group = Events(config.minimum, max(1.6 * config.ai_interval, 1.6 / config.fps))
    next_ai = config.start_seconds
    ai_scans = 0
    ai_readable = 0
    ai_checks = []
    ai_unavailable = None
    ai_inspection = {
        "region_policy": "whole_laptop_or_direct_screen",
        "independent_of_screen_changes": True,
        "regions_scanned": 0,
    }
    scanner = scanner or InterfaceScanner()
    tracks = Tracks(timeout=max(1.0, 2 / config.fps))
    screen = ScreenChanges(config.minimum)
    screen_events = []
    has_camera = config.mode != "screen"
    has_screen = config.mode in {"screen", "combined"} or (
        config.mode == "external"
        and (config.screen_corners is not None or config.auto_screen)
    )
    auto_display = (
        config.mode == "external"
        and config.screen_corners is None
        and config.auto_screen
    )
    display_tracker = DisplayTracker()
    screen_anchor_view = None
    screen_anchor_seconds = None
    screen_localization = {"mode": "automatic" if auto_display else "manual_or_direct"}
    last_screen_time = None
    last_screen_corners = None
    screen_gaps = []
    screen_gap = None
    calibration_valid = True
    previous_camera = None
    previous_size = None
    frame_count = 0
    last_time = 0.0
    coverage = Counter()
    try:
        detector = detector or (
            Detector(models, config.threshold) if has_camera else None
        )
        for timestamp, image in frames(source, config.fps):
            if timestamp < config.start_seconds:
                continue
            if config.end_seconds is not None and timestamp > config.end_seconds:
                break
            frame_count += 1
            last_time = timestamp
            observations = {}
            screen_usable = False
            objects = []
            drawn = image
            camera = crop(image, config.camera_roi) if has_camera else None
            size = image.shape[:2]
            hsv = (
                cv2.cvtColor(cv2.resize(camera, (160, 100)), cv2.COLOR_BGR2HSV)
                if camera is not None
                else None
            )
            cut = has_camera and (
                previous_size is not None
                and (size != previous_size or shot_changed(previous_camera, hsv))
            )
            if cut:
                group.boundary()
                ai_group.boundary()
                tracks = Tracks()
                counts["scene_boundaries"] += 1
                if config.mode == "external" and has_screen:
                    calibration_valid = auto_display
                    display_tracker = DisplayTracker()
                    screen = ScreenChanges(config.minimum)
                    screen_anchor_view = None
                    screen_anchor_seconds = None
                    last_screen_corners = None
            previous_camera = hsv
            previous_size = size
            inference_image = camera.copy() if has_camera else None
            if has_camera:
                for region in config.ignore_regions or []:
                    crop(inference_image, region)[:] = 0
            if has_camera and quality(inference_image):
                coverage["people"] += 1
                objects = detector.predict(inference_image)
                tracked = tracks.update(objects, timestamp)
                people = [(k, o, p) for k, o, p in tracked if o.label == "person"]
                clear_people = [
                    item for item in people if clear_person(camera, item[1])
                ]
                ambiguous = [
                    item for item in people if not clear_person(camera, item[1])
                ]
                phones = [(k, o, p) for k, o, p in tracked if o.label == "phone"]
                coverage["phone_presence"] += 1
                hand_visible = any(
                    any(key.endswith("wrist") for key in (o.points or {}))
                    for _, o, _ in people
                )
                if hand_visible:
                    coverage["phone_interaction"] += 1
                    if not config.phone_placement:
                        coverage["phone_use_risk"] += 1
                if len(clear_people) >= 2:
                    observations["additional_person_candidate"] = (
                        min(o.score for _, o, _ in clear_people),
                        {
                            "reason": f"{len(clear_people)} sufficiently visible person detections. Reflections/displayed images still require review; identities are not inferred.",
                            "person_count": len(clear_people),
                        },
                    )
                if clear_people and ambiguous:
                    observations["ambiguous_person_candidate"] = (
                        max(o.score for _, o, _ in ambiguous),
                        {
                            "reason": "A low-contrast person-like silhouette is present; it is not counted as a verified additional person."
                        },
                    )
                if phones:
                    observations["phone_present"] = (
                        max(o.score for _, o, _ in phones),
                        {
                            "reason": "A phone is visible; visibility alone does not establish use."
                        },
                    )
                for _, phone, old_phone in phones:
                    for _, person, old_person in people:
                        signals = interaction(
                            phone,
                            person,
                            old_phone[0] if old_phone else None,
                            old_person[0] if old_person else None,
                        )
                        if signals["contact"]:
                            score = min(phone.score, person.score)
                            kind = "possible_phone_interaction"
                            if score > observations.get(kind, (0, {}))[0]:
                                observations[kind] = (
                                    score,
                                    {
                                        "reason": "A detected wrist remains near a phone; actual operation is unverified."
                                    },
                                )
                        if signals["use"]:
                            kind = "possible_phone_use"
                            score = min(phone.score, person.score)
                            if score > observations.get(kind, (0, {}))[0]:
                                observations[kind] = (
                                    score,
                                    {
                                        "reason": "Hand–phone proximity with near-head position or coupled movement.",
                                        "signals": signals,
                                    },
                                )
                laptops_camera = [o for o in objects if o.label == "laptop"]
                if config.phone_placement:
                    if laptops_camera or hand_visible:
                        coverage["phone_use_risk"] += 1
                    confirmed = positioned_phones(
                        [o for _, o, _ in phones], laptops_camera
                    )
                    candidates = phone_shaped_obstructions(
                        inference_image, laptops_camera
                    )
                    if confirmed or candidates:
                        target = (confirmed or candidates)[0]
                        details = {
                            "reason": "A portrait object is positioned against the laptop display, allowing hands-free viewing. Active operation is unverified.",
                            "identity": "model_confirmed_phone"
                            if confirmed
                            else "uncertain_phone_shaped_obstruction",
                            "basis": "portrait_phone_overlapping_laptop"
                            if confirmed
                            else "dark_portrait_geometry_in_laptop_area",
                            "bounding_box": [round(v, 1) for v in target.box],
                            "hand_contact_required": False,
                        }
                        observations[
                            "phone_positioned_for_viewing"
                            if confirmed
                            else "phone_placement_candidate"
                        ] = (target.score, details.copy())
                        if (
                            target.score
                            > observations.get("possible_phone_use", (0, {}))[0]
                        ):
                            observations["possible_phone_use"] = (
                                target.score,
                                details.copy(),
                            )
                        objects.extend(candidates)
                drawn = annotate(camera, objects)
            else:
                if has_camera:
                    counts["camera_quality_rejected"] += 1
                    group.boundary()
            if (
                config.ai_scan
                and config.mode != "webcam"
                and timestamp + 1e-6 >= next_ai
            ):
                next_ai = timestamp + config.ai_interval
                ai_scans += 1
                ai_observations = {}
                regions = []
                if config.mode in {"screen", "combined"}:
                    regions = [
                        (crop(image, config.screen_roi), image, "screen_region", None)
                    ]
                elif camera is not None and quality(inference_image):
                    for laptop in objects:
                        if laptop.label != "laptop":
                            continue
                        x, y, r, b = map(int, laptop.box)
                        x, y = max(0, x), max(0, y)
                        r, b = min(camera.shape[1], r), min(camera.shape[0], b)
                        if r > x and b > y:
                            regions.append(
                                (
                                    inference_image[y:b, x:r],
                                    drawn,
                                    "whole_laptop_in_camera_crop",
                                    [x, y, r, b],
                                )
                            )
                    if (
                        not regions
                        and config.screen_corners is not None
                        and calibration_valid
                    ):
                        regions = [
                            (
                                extract(image, None, config.screen_corners),
                                image,
                                "manual_display",
                                None,
                            )
                        ]
                regions.sort(
                    key=lambda entry: entry[0].shape[0] * entry[0].shape[1],
                    reverse=True,
                )
                readable = False
                if ai_unavailable is None:
                    for region, context, region_type, box in regions:
                        ai_inspection["regions_scanned"] += 1
                        inspection = context.copy()
                        if box is not None:
                            cv2.rectangle(
                                inspection,
                                tuple(box[:2]),
                                tuple(box[2:]),
                                (0, 220, 255),
                                2,
                            )
                        if "first_preview" not in ai_inspection:
                            if not cv2.imwrite(
                                str(evidence / "ai-inspection-first.jpg"), inspection
                            ):
                                raise OSError("Cannot write AI inspection preview")
                            ai_inspection["first_preview"] = (
                                "evidence/ai-inspection-first.jpg"
                            )
                            ai_inspection["first_scan_seconds"] = round(timestamp, 3)
                        # Show the largest inspected laptop, while scanning all laptops.
                        if ai_inspection.get("latest_scan_seconds") != round(
                            timestamp, 3
                        ):
                            if not cv2.imwrite(
                                str(evidence / "ai-inspection-latest.jpg"), inspection
                            ):
                                raise OSError("Cannot write AI inspection preview")
                            ai_inspection["latest_preview"] = (
                                "evidence/ai-inspection-latest.jpg"
                            )
                            ai_inspection["latest_scan_seconds"] = round(timestamp, 3)
                            ai_inspection["latest_region_box"] = box
                        try:
                            result = scanner.scan(region)
                        except Exception as error:
                            ai_unavailable = type(error).__name__
                            break
                        readable = readable or result["readable"]
                        if result["match"]:
                            kind = (
                                "ai_interface_candidate"
                                if result["match"] == "unidentified_ai_assistant"
                                else "ai_interface_visible"
                            )
                            score = result["score"]
                            if score <= ai_observations.get(kind, (0, {}))[0]:
                                continue
                            name = f"ai-{frame_count:07}-{len(ai_observations)}.jpg"
                            if not cv2.imwrite(str(evidence / name), context):
                                raise OSError("Cannot write AI evidence screenshot")
                            ai_observations[kind] = (
                                score,
                                {
                                    "reason": "An AI interface header and chat control are readable. Visibility does not establish that assistance was requested or used.",
                                    "service": result["match"],
                                    "matched_cues": result["matched_cues"],
                                    "identity_basis": result["identity_basis"],
                                    "screenshot": f"evidence/{name}",
                                    "evidence_region": region_type,
                                    "bounding_box": box,
                                    "evidence_timestamp_seconds": round(timestamp, 3),
                                    "source": "local_ocr",
                                },
                            )
                ai_checks.append(
                    {"time_seconds": timestamp, "readable": bool(readable)}
                )
                ai_readable += int(readable)
                if not regions:
                    counts["ai_no_region"] += 1
                elif not readable:
                    counts["ai_text_unreadable"] += 1
                ai_group.update(timestamp, ai_observations)
            corners = config.screen_corners
            localization = None
            if auto_display:
                dx = round((config.camera_roi or [0, 0, 1, 1])[0] * image.shape[1])
                dy = round((config.camera_roi or [0, 0, 1, 1])[1] * image.shape[0])
                laptops = [
                    Object(
                        "laptop",
                        (o.box[0] + dx, o.box[1] + dy, o.box[2] + dx, o.box[3] + dy),
                        o.score,
                    )
                    for o in objects
                    if o.label == "laptop"
                ]
                localization = display_tracker.update(image, laptops)
                corners = localization[0] if localization else None
                if corners is None:
                    counts["screen_not_localized"] += 1

            if (
                has_screen
                and calibration_valid
                and (not auto_display or corners is not None)
            ):
                view = extract(
                    image,
                    config.screen_roi,
                    corners if config.mode == "external" else None,
                )
                if quality(view):
                    screen_usable = True
                    coverage["screen"] += 1
                    last_screen_time = timestamp
                    if screen_anchor_view is None:
                        screen_anchor_view = view.copy()
                        screen_anchor_seconds = timestamp
                    if "preview" not in screen_localization:
                        cv2.imwrite(str(evidence / "display-preview.jpg"), view)
                        preview = image.copy()
                        if corners is not None:
                            cv2.polylines(
                                preview,
                                [
                                    np.int32(
                                        np.array(corners)
                                        * [image.shape[1] - 1, image.shape[0] - 1]
                                    )
                                ],
                                True,
                                (0, 220, 255),
                                3,
                            )
                        cv2.imwrite(str(evidence / "display-location.jpg"), preview)
                        screen_localization.update(
                            {
                                "preview": "evidence/display-preview.jpg",
                                "location_preview": "evidence/display-location.jpg",
                                "first_usable_seconds": round(timestamp, 3),
                            }
                        )
                    transition = screen.update(
                        timestamp,
                        view,
                        comparable=compatible_regions(last_screen_corners, corners),
                    )
                    last_screen_corners = corners
                    if transition:
                        name = f"screen-{frame_count:07}.jpg"
                        if not cv2.imwrite(str(evidence / name), image):
                            raise OSError("Cannot write evidence screenshot")
                        transition["screenshot"] = f"evidence/{name}"
                        before = f"screen-{frame_count:07}-before.jpg"
                        after = f"screen-{frame_count:07}-after.jpg"
                        if not cv2.imwrite(
                            str(evidence / before), screen_anchor_view
                        ) or not cv2.imwrite(str(evidence / after), view):
                            raise OSError("Cannot write screen transition evidence")
                        transition.update(
                            {
                                "before_screenshot": f"evidence/{before}",
                                "before_timestamp_seconds": round(
                                    screen_anchor_seconds, 3
                                ),
                                "after_timestamp_seconds": round(timestamp, 3),
                                "after_screenshot": f"evidence/{after}",
                                "display_corners": corners,
                                "localization_method": localization[2]
                                if localization
                                else "manual_or_direct",
                            }
                        )
                        screen_anchor_view = view.copy()
                        screen_anchor_seconds = timestamp
                        screen_events.append(transition)
                    elif screen.last_baseline == timestamp:
                        # Keep the latest comparable baseline, not the first frame
                        # of a long stable period, for truthful before evidence.
                        screen_anchor_view = view.copy()
                        screen_anchor_seconds = timestamp
                else:
                    counts["screen_quality_rejected"] += 1
            if has_screen:
                if not screen_usable:
                    screen.missing(timestamp)
                    if screen_gap is None:
                        screen_gap = {
                            "first_missing_seconds": round(timestamp, 3),
                            "last_usable_seconds": round(last_screen_time, 3)
                            if last_screen_time is not None
                            else None,
                            "reason": "Display unavailable, uncalibrated, or below image-quality requirements.",
                        }
                elif screen_gap is not None:
                    screen_gap["resumed_seconds"] = round(timestamp, 3)
                    screen_gaps.append(screen_gap)
                    screen_gap = None
            for kind, (score, details) in list(observations.items()):
                active = group.active.get(kind)
                if (
                    active is None
                    or timestamp - active.last > group.gap
                    or score > active.peak
                ):
                    name = f"camera-{frame_count:07}.jpg"
                    if not (evidence / name).exists() and not cv2.imwrite(
                        str(evidence / name), drawn
                    ):
                        raise OSError("Cannot write evidence screenshot")
                    details["screenshot"] = f"evidence/{name}"
                    details["evidence_timestamp_seconds"] = round(timestamp, 3)
                    details["evidence_region"] = "camera_crop"
                else:
                    details = active.evidence
                observations[kind] = (score, details)
            group.update(timestamp, observations)
            if progress and frame_count % 4 == 0:
                progress(timestamp, frame_count)
        if frame_count == 0:
            raise ValueError("No video frames decoded")
        if screen_gap is not None:
            screen_gap["resumed_seconds"] = None
            screen_gap["unavailable_through_seconds"] = round(last_time, 3)
            screen_gaps.append(screen_gap)
        events = group.close() + ai_group.close() + screen_events
        for event in screen_events:
            if event["type"] != "screen_content_changed":
                continue
            nearby = [
                check
                for check in ai_checks
                if event["start_seconds"] - config.ai_interval
                <= check["time_seconds"]
                <= event["end_seconds"] + config.ai_interval
            ]
            related = [
                other
                for other in events
                if other["type"] in {"ai_interface_visible", "ai_interface_candidate"}
                and other["start_seconds"] <= event["end_seconds"] + config.ai_interval
                and other["end_seconds"] >= event["start_seconds"] - config.ai_interval
            ]
            readable_nearby = sum(check["readable"] for check in nearby)
            event["ai_interface_check"] = {
                "result": "candidate_detected"
                if related
                else "not_assessable"
                if not nearby or readable_nearby / len(nearby) < 0.6
                else "no_event_observed",
                "scheduled_scans": len(nearby),
                "readable_scans": readable_nearby,
                "services": sorted({other["service"] for other in related}),
                "reason": "AI recognition near this visual change is a separate identity check. Unreadable text does not prevent a screen-change alert; nearby interface visibility does not establish the destination or active assistance.",
            }
        if telemetry:
            raw = json.loads(Path(telemetry).read_text())
            recorded = raw.get("events", []) if isinstance(raw, dict) else raw
            if not isinstance(recorded, list):
                raise ValueError(
                    "Telemetry must be an event list or an object with an events list"
                )
            for item in recorded:
                t = float(item["time_seconds"])
                if not math.isfinite(t) or t < 0 or t > last_time + 1 / config.fps:
                    raise ValueError("Telemetry timestamp is outside this recording")
                kind = item["type"]
                if kind not in {
                    "page_hidden",
                    "window_blur",
                    "fullscreen_exit",
                    "foreground_app_changed",
                }:
                    raise ValueError("Unsupported telemetry event type")
                events.append(
                    {
                        "type": kind,
                        "start_seconds": t,
                        "end_seconds": t,
                        "duration_seconds": 0,
                        "source": "provided_telemetry",
                        "reason": "Recorded client event; source authenticity and clock alignment must be verified.",
                    }
                )
        assessments = {}
        for capability, key, kinds, enabled in [
            (
                "additional_person",
                "people",
                {"additional_person_candidate"},
                has_camera,
            ),
            ("phone_presence", "phone_presence", {"phone_present"}, has_camera),
            (
                "phone_interaction",
                "phone_interaction",
                {"possible_phone_interaction"},
                has_camera,
            ),
            (
                "phone_use_risk",
                "phone_use_risk",
                {"possible_phone_use"},
                has_camera,
            ),
            (
                "screen_changes",
                "screen",
                {"screen_content_changed", "foreground_app_changed"},
                has_screen or bool(telemetry),
            ),
        ]:
            ratio = coverage[key] / frame_count
            observed = any(e["type"] in kinds for e in events)
            assessments[capability] = {
                "result": "candidate_detected"
                if observed
                else "not_assessable"
                if not enabled or ratio < 0.6
                else "no_event_observed",
                "assessable_sample_fraction": round(ratio, 3),
            }
        ai_ratio = ai_readable / ai_scans if ai_scans else 0
        ai_observed = any(
            e["type"] in {"ai_interface_visible", "ai_interface_candidate"}
            for e in events
        )
        assessments["ai_interface"] = {
            "result": "candidate_detected"
            if ai_observed
            else "not_assessable"
            if ai_ratio < 0.6 or ai_unavailable
            else "no_event_observed",
            "assessable_sample_fraction": round(ai_ratio, 3),
            "scheduled_scans": ai_scans,
            "readable_scans": ai_readable,
            "reason": "disabled_or_camera_only"
            if not config.ai_scan or config.mode == "webcam"
            else "ocr_unavailable_" + ai_unavailable
            if ai_unavailable
            else "AI service recognition requires readable header identity and chat controls; unreadable text cannot exclude AI interfaces.",
        }
        report = {
            "analysis_version": "0.4.4",
            "status": "success",
            "source_video": source.name,
            "mode": config.mode,
            "configuration": asdict(config),
            "software_versions": {
                name: version(name)
                for name in (
                    "ultralytics",
                    "av",
                    "opencv-python",
                    "numpy",
                    "rapidocr-onnxruntime",
                    "onnxruntime",
                )
            },
            "model_checksums": json.loads((Path(models) / "checksums.json").read_text())
            if has_camera and (Path(models) / "checksums.json").is_file()
            else {},
            "sample_fps": config.fps,
            "sample_count": frame_count,
            "last_sample_seconds": round(last_time, 3),
            "assessments": assessments,
            "diagnostics": dict(counts),
            "ai_inspection": ai_inspection,
            "screen_localization": {
                **screen_localization,
                "usable_samples": coverage["screen"],
                "tracking_gaps": screen_gaps,
            },
            "events": sorted(events, key=lambda e: e["start_seconds"]),
            "limitations": [
                "Events are visual observations and heuristic candidates, not misconduct verdicts.",
                "Hidden objects and activity outside recorded surfaces cannot be assessed.",
                "Visual screen changes do not verify application or tab identity.",
                "Phone placement risk does not require wrists. Geometry candidates do not verify phone identity or active use.",
                "AI recognition uses periodic local OCR on the whole laptop or provided screen region, independently of visual transitions. Small/blurred text, unknown services, non-English controls and mimicked interfaces can be missed or misclassified.",
                "External screen calibration is invalidated after detected scene cuts.",
                "Short display gaps retain a comparable baseline for up to five seconds; transition timing across gaps is uncertain. Region changes and longer gaps explicitly reset comparison.",
                "Scene-cut and quality checks are heuristics; review evidence and coverage.",
            ],
        }
        referenced = {event["screenshot"] for event in events if "screenshot" in event}
        for event in events:
            referenced.update(
                event[key]
                for key in ("before_screenshot", "after_screenshot")
                if key in event
            )
        referenced.update(
            screen_localization[key]
            for key in ("preview", "location_preview")
            if key in screen_localization
        )
        referenced.update(
            ai_inspection[key]
            for key in ("first_preview", "latest_preview")
            if key in ai_inspection
        )
        for path in evidence.iterdir():
            if f"evidence/{path.name}" not in referenced:
                path.unlink()
        report = review_report(report)
        write_review_html(report, output)
        write_report_pdf(report, output)
        write_json(output / "report.json", report)
        return report
    except Exception as error:
        write_json(
            output / "report.json",
            {
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
