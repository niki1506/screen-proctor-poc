"""Find a text-bearing display within a detected laptop, without fixed coordinates."""

import cv2
import numpy as np

from .screen import extract
from .borders import border_quads


def ordered(points):
    points = np.asarray(points, np.float32).reshape(4, 2)
    center = points.mean(axis=0)
    points = points[
        np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    ]
    return np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)


def text_support(image):
    gray = cv2.cvtColor(cv2.resize(image, (400, 250)), cv2.COLOR_BGR2GRAY)
    support = 0
    # Characters on both bright and dark interfaces. Ignore panel-sized shapes.
    for binary in (
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
    ):
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary)
        support += sum(
            2 <= h <= 18 and 1 <= w <= 45 and 3 <= area <= 350
            for x, y, w, h, area in stats[1:count]
        )
    return support


def text_region(image, laptops):
    height, width = image.shape[:2]
    ranked = []
    for laptop in laptops:
        x, y, r, b = map(int, laptop.box)
        x, y = max(0, x), max(0, y)
        r, b = min(width, r), min(height, b)
        region = image[y:b, x:r]
        if min(region.shape[:2], default=0) < 60:
            continue
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        masks = [cv2.Canny(gray, 40, 120)]
        masks += [
            cv2.threshold(gray, v, 255, cv2.THRESH_BINARY)[1]
            for v in (80, 120, 160, 200)
        ]
        for mask in masks:
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                poly = cv2.approxPolyDP(
                    contour, 0.025 * cv2.arcLength(contour, True), True
                )
                if len(poly) != 4 or not cv2.isContourConvex(poly):
                    continue
                area = cv2.contourArea(poly)
                if (
                    not 0.13 * region.shape[0] * region.shape[1]
                    < area
                    < 0.92 * region.shape[0] * region.shape[1]
                ):
                    continue
                points = ordered(poly)
                # A laptop display lies above its keyboard in the detector's box.
                if points[:, 1].mean() > 0.72 * region.shape[0]:
                    continue
                top = np.linalg.norm(points[1] - points[0])
                side = np.linalg.norm(points[3] - points[0])
                if not 0.85 < top / max(side, 1) < 3:
                    continue
                points += np.array([x, y], np.float32)
                normalized = points / np.array([width - 1, height - 1], np.float32)
                try:
                    view = extract(image, corners=normalized)
                except ValueError:
                    continue
                letters = text_support(view)
                if letters < 12 or np.std(cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)) < 12:
                    continue
                ranked.append(
                    (area, normalized.tolist(), min(0.95, 0.6 + letters / 500))
                )
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1], ranked[0][2]


def polygon_iou(a, b):
    # OpenCV intersection tolerances are unstable for nearly coincident sub-unit edges.
    # Work in pixel-like units; the area ratio is invariant to this shared scale.
    a, b = np.asarray(a, np.float32) * 1000, np.asarray(b, np.float32) * 1000
    overlap, _ = cv2.intersectConvexConvex(a, b)
    union = cv2.contourArea(a) + cv2.contourArea(b) - overlap
    return float(overlap / union) if union > 0 else 0.0


def physical_screen(image, laptops):
    """Prefer the outer display border over an internal bright application pane."""
    height, width = image.shape[:2]
    candidates = []
    for laptop in laptops:
        x, y, r, b = map(int, laptop.box)
        x, y = max(0, x), max(0, y)
        r, b = min(width, r), min(height, b)
        region = image[y:b, x:r]
        if min(region.shape[:2], default=0) < 60:
            continue
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        for points, support, area in border_quads(gray):
            normalized = (points + [x, y]) / [width - 1, height - 1]
            try:
                view = extract(image, corners=normalized)
            except ValueError:
                continue
            # Require content evidence on first acquisition, excluding blank backs.
            if (
                text_support(view) < 8
                or np.std(cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)) < 8
            ):
                continue
            candidates.append((area, normalized.tolist(), support))
    if not candidates:
        return None
    _, points, support = max(candidates, key=lambda item: item[0])
    return points, support


def locate_screen(image, laptops):
    return physical_screen(image, laptops) or text_region(image, laptops)


def compatible_regions(a, b):
    """Reject a pane-sized replacement for a previously tracked full display."""
    if a is None or b is None:
        return True
    a, b = np.float32(a), np.float32(b)
    ratio = cv2.contourArea(b) / max(cv2.contourArea(a), 1e-9)
    return 0.7 <= ratio <= 1.45 and polygon_iou(a, b) > 0.4


class DisplayTracker:
    """Track a display border, reacquiring from a laptop when optical flow fails."""

    def __init__(self):
        self.gray = None
        self.corners = None
        self.reference = None

    def update(self, image, laptops):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        result = None
        if (
            self.gray is not None
            and self.gray.shape == gray.shape
            and self.corners is not None
        ):
            polygon = np.float32(np.array(self.corners) * [width - 1, height - 1])
            filled = np.zeros_like(gray)
            cv2.fillConvexPoly(filled, np.int32(np.rint(polygon)), 255)
            kernel = np.ones((21, 21), np.uint8)
            ring = cv2.subtract(cv2.dilate(filled, kernel), cv2.erode(filled, kernel))
            points = cv2.goodFeaturesToTrack(self.gray, 160, 0.01, 4, mask=ring)
            if points is not None and len(points) >= 8:
                moved, status, _ = cv2.calcOpticalFlowPyrLK(
                    self.gray, gray, points, None
                )
                if moved is not None:
                    back, back_status, _ = cv2.calcOpticalFlowPyrLK(
                        gray, self.gray, moved, None
                    )
                    if back is not None:
                        valid = (
                            (status.ravel() > 0)
                            & (back_status.ravel() > 0)
                            & (np.linalg.norm(points - back, axis=2).ravel() < 1.5)
                        )
                        if valid.sum() >= 8:
                            matrix, inliers = cv2.findHomography(
                                points[valid], moved[valid], cv2.RANSAC, 3
                            )
                            if matrix is not None and inliers.mean() >= 0.6:
                                tracked = cv2.perspectiveTransform(
                                    np.float32(polygon).reshape(1, 4, 2), matrix
                                )[0]
                                normal = tracked / np.array(
                                    [width - 1, height - 1], np.float32
                                )
                                if (
                                    cv2.isContourConvex(tracked)
                                    and (normal >= 0).all()
                                    and (normal <= 1).all()
                                    and polygon_iou(normal, self.corners) > 0.55
                                ):
                                    result = (
                                        normal.tolist(),
                                        float(inliers.mean()),
                                        "tracked_display_border",
                                    )
        physical = physical_screen(image, laptops)
        if physical is not None:
            # Upgrade a pane track when an enclosing physical border is visible.
            tracked_area = cv2.contourArea(np.float32(result[0])) if result else 0
            physical_area = cv2.contourArea(np.float32(physical[0]))
            if result is None or physical_area > tracked_area * 1.18:
                result = (physical[0], float(physical[1]), "detected_display_border")
        if result is None:
            found = text_region(image, laptops)
            if found is not None and compatible_regions(self.reference, found[0]):
                result = (found[0], float(found[1]), "detected_text_bearing_display")
        if result is not None:
            self.reference = result[0]
        self.gray = gray
        self.corners = result[0] if result else None
        return result
