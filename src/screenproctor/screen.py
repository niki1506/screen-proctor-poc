"""Calibrated screen extraction and stable visual transitions, not app identity."""

import cv2
import numpy as np

from .video import crop


def extract(image, roi=None, corners=None):
    if corners is None:
        return crop(image, roi)
    points = np.asarray(corners, dtype=np.float32)
    if (
        points.shape != (4, 2)
        or not np.isfinite(points).all()
        or (points < 0).any()
        or (points > 1).any()
    ):
        raise ValueError("Corners must be normalized TL,TR,BR,BL coordinates")
    points = points * np.array([image.shape[1] - 1, image.shape[0] - 1], np.float32)
    if (
        not cv2.isContourConvex(points.reshape(-1, 1, 2))
        or cv2.contourArea(points) < 400
    ):
        raise ValueError(
            "Screen corners must form a sufficiently large convex quadrilateral"
        )
    width = round(
        max(
            np.linalg.norm(points[1] - points[0]), np.linalg.norm(points[2] - points[3])
        )
    )
    height = round(
        max(
            np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[2] - points[1])
        )
    )
    if min(width, height) < 32:
        raise ValueError("Visible screen is too small")
    matrix = cv2.getPerspectiveTransform(
        points,
        np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]),
    )
    return cv2.warpPerspective(image, matrix, (width, height))


class ScreenChanges:
    def __init__(self, dwell=0.75):
        self.dwell = dwell
        self.anchor = None
        self.previous = None
        self.candidate_start = None
        self.candidate_view = None
        self.candidate_peak = 0.0
        self.last_usable = None
        self.last_baseline = None
        self.gap_from = None
        self.gap_context = None

    @staticmethod
    def representation(image):
        return cv2.GaussianBlur(cv2.resize(image, (320, 200)), (5, 5), 0)

    @staticmethod
    def distance(a, b):
        # Small registration errors and exposure shifts are common when filming
        # a physical display. Align only small, highly correlated transformations.
        aligned = b
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            correlation, warp = cv2.findTransformECC(
                cv2.cvtColor(a, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(b, cv2.COLOR_BGR2GRAY),
                warp,
                cv2.MOTION_AFFINE,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.001),
            )
            if (
                correlation > 0.8
                and np.max(np.abs(warp[:, :2] - np.eye(2))) < 0.08
                and np.max(np.abs(warp[:, 2])) < 12
            ):
                aligned = cv2.warpAffine(
                    b,
                    warp,
                    (a.shape[1], a.shape[0]),
                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_REFLECT,
                )
        except cv2.error:
            pass
        shift = np.clip(np.median(aligned.astype(np.float32) - a, axis=(0, 1)), -15, 15)
        difference = np.max(np.abs(aligned.astype(np.float32) - a - shift), axis=2) > 30
        pixel_fraction = float(np.mean(difference[3:-3, 3:-3]))
        # Muted text on a white page can change throughout the display without
        # exceeding the 30-level color threshold. Compare text/layout edges too.
        # A one-pixel neighborhood tolerates residual tracking/compression jitter.
        gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        margin = min(10, max(1, min(gray_a.shape) // 10))
        edges_a = cv2.Canny(gray_a, 10, 30)[margin:-margin, margin:-margin] > 0
        edges_b = cv2.Canny(gray_b, 10, 30)[margin:-margin, margin:-margin] > 0
        kernel = np.ones((3, 3), np.uint8)
        near_a = cv2.dilate(edges_a.astype(np.uint8), kernel) > 0
        near_b = cv2.dilate(edges_b.astype(np.uint8), kernel) > 0
        unmatched = (edges_a & ~near_b) | (edges_b & ~near_a)
        edge_count = int(edges_a.sum() + edges_b.sum())
        # Require a substantial proportion of the existing structure to change;
        # isolated cursor changes and slight edge noise should not trigger this.
        structural_fraction = (
            float(unmatched.mean())
            if edge_count and unmatched.sum() / edge_count > 0.25
            else 0.0
        )
        return max(pixel_fraction, structural_fraction)

    def missing(self, timestamp):
        """Break positive support while retaining the last comparable stable view."""
        if self.anchor is not None and self.gap_from is None:
            self.gap_from = self.last_usable
        self.previous = None
        self.candidate_start = None
        self.candidate_view = None

    def update(self, timestamp, image, comparable=True):
        current = self.representation(image)
        if self.anchor is not None and (
            not comparable
            or self.gap_from is not None
            and timestamp - self.gap_from > 5
        ):
            reason = (
                "display_region_changed"
                if not comparable
                else "screen_gap_exceeded_comparison_limit"
            )
            previous_time = self.last_usable
            self.anchor = current
            self.previous = current
            self.last_baseline = timestamp
            self.last_usable = timestamp
            self.candidate_start = None
            self.candidate_view = None
            self.gap_from = None
            self.gap_context = None
            return {
                "type": "screen_comparison_reset",
                "start_seconds": round(timestamp, 3),
                "end_seconds": round(timestamp, 3),
                "duration_seconds": 0,
                "reason": "The screen could not be compared reliably with the previous view. Activity during this interval remains unassessed.",
                "reset_cause": reason,
                "last_comparable_seconds": previous_time,
                "application_identity": "unidentified",
            }
        if self.gap_from is not None:
            self.gap_context = {
                "last_usable_seconds": round(self.gap_from, 3),
                "resumed_seconds": round(timestamp, 3),
            }
            self.gap_from = None
        self.last_usable = timestamp
        if self.anchor is None:
            self.anchor = current
            self.last_baseline = timestamp
            self.previous = current
            return None
        changed = self.distance(current, self.anchor)
        motion = (
            self.distance(current, self.previous) if self.previous is not None else 0.0
        )
        self.previous = current
        # Wait for a changed view to settle; avoid interpreting a scrolling animation
        # as multiple application switches. A settled scroll can still be a content change.
        if changed < 0.08:
            self.last_baseline = timestamp
            self.gap_context = None
            self.candidate_start = None
            self.candidate_view = None
            return None
        candidate_changed = (
            self.candidate_view is not None
            and self.distance(current, self.candidate_view) >= 0.08
        )
        if self.candidate_start is None or motion > 0.12 or candidate_changed:
            self.candidate_start = timestamp
            self.candidate_view = current
            self.candidate_peak = changed
        self.candidate_peak = max(self.candidate_peak, changed)
        if timestamp - self.candidate_start < self.dwell:
            return None
        header = self.distance(current[:35], self.anchor[:35])
        result = {
            "type": "screen_content_changed",
            "label": "Screen change",
            "confirmed_at_seconds": round(timestamp, 3),
            "start_seconds": round(self.candidate_start, 3),
            "end_seconds": round(timestamp, 3),
            "duration_seconds": round(timestamp - self.candidate_start, 3),
            "changed_fraction": round(self.candidate_peak, 3),
            "comparison_metric": "max_color_or_unmatched_edge_fraction",
            "possible_screen_switch": bool(
                changed > 0.35 or (changed > 0.08 and header > 0.12)
            ),
            "evidence_score": round(min(0.95, 0.45 + changed * 0.5), 3),
            "score_is_calibrated_probability": False,
            "application_identity": "unidentified",
            "change_window_start_seconds": round(self.last_baseline, 3),
            "change_window_end_seconds": round(self.candidate_start, 3),
            "reason": "A visible screen layout or content change was detected. Scrolling, physical occlusion, or residual alignment error may explain it; application/tab identity is not verified.",
        }
        if self.gap_context is not None:
            result["comparison_gap"] = self.gap_context
            result["onset_is_uncertain"] = True
            result["reason"] += (
                " The comparison spans a tracking gap; the exact transition time is unknown."
            )
            self.gap_context = None
        # Adopt a new stable anchor so B -> C is detected without returning to A.
        self.anchor = current
        self.last_baseline = timestamp
        self.candidate_start = None
        self.candidate_view = None
        return result
