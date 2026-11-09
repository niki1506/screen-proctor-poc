"""Display-border hypotheses supported by long image edges, not panel brightness."""

from itertools import combinations

import cv2
import numpy as np


def intersection(a, b):
    p, q = a[:2], b[:2]
    u, v = a[2:] - p, b[2:] - q
    cross = float(u[0] * v[1] - u[1] * v[0])
    if abs(cross) < 1e-5:
        return None
    return p + u * (float((q - p)[0] * v[1] - (q - p)[1] * v[0]) / cross)


def border_quads(gray):
    """Return quads whose four sides have visible edge support in a laptop ROI."""
    h, w = gray.shape
    lines = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    if lines is None:
        return []
    horizontal = []
    vertical = []
    for segment in lines[:, 0, :]:
        x, y, r, b = segment
        dx, dy = abs(r - x), abs(b - y)
        length = float(np.hypot(dx, dy))
        if max(y, b) > 0.87 * h:
            continue
        if dx >= 0.30 * w and dy < 0.5 * dx:
            horizontal.append((length, segment))
        elif dy >= 0.12 * h and dy > 1.1 * dx:
            vertical.append((length, segment))
    horizontal = [
        s for _, s in sorted(horizontal, key=lambda x: x[0], reverse=True)[:14]
    ]
    vertical = [s for _, s in sorted(vertical, key=lambda x: x[0], reverse=True)[:28]]
    edges = cv2.Canny(gray, 25, 90)
    distances = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3)
    candidates = []
    for a, b in combinations(horizontal, 2):
        a, b = sorted((a, b), key=lambda s: float((s[1] + s[3]) / 2))
        if (b[1] + b[3] - a[1] - a[3]) / 2 < 0.25 * h:
            continue
        if abs((a[3] - a[1]) / (a[2] - a[0]) - (b[3] - b[1]) / (b[2] - b[0])) > 0.3:
            continue
        for left, right in combinations(vertical, 2):
            left, right = sorted((left, right), key=lambda s: float((s[0] + s[2]) / 2))
            if (right[0] + right[2] - left[0] - left[2]) / 2 < 0.40 * w:
                continue
            points = [
                intersection(a, left),
                intersection(a, right),
                intersection(b, right),
                intersection(b, left),
            ]
            if any(p is None for p in points):
                continue
            points = np.float32(points)
            if not cv2.isContourConvex(points):
                continue
            if (
                points[:, 0].min() < 0
                or points[:, 0].max() >= w
                or points[:, 1].min() < 0
                or points[:, 1].max() >= h
            ):
                continue
            if np.mean(points[:2, 1]) > 0.35 * h or np.mean(points[2:, 1]) > 0.84 * h:
                continue
            area = cv2.contourArea(points)
            top = np.linalg.norm(points[1] - points[0])
            side = np.linalg.norm(points[3] - points[0])
            if (
                not 0.12 * w * h < area < 0.68 * w * h
                or not 1.05 < top / max(side, 1) < 3.2
            ):
                continue
            support = []
            for p, q in zip(points, np.roll(points, -1, axis=0), strict=True):
                samples = p + (q - p) * np.linspace(0.03, 0.97, 60)[:, None]
                coords = np.rint(samples).astype(int)
                coords = np.clip(coords, [0, 0], [w - 1, h - 1])
                support.append(
                    float(np.mean(distances[coords[:, 1], coords[:, 0]] < 2.5))
                )
            if min(support) < 0.65 or np.mean(support) < 0.90:
                continue
            if any(
                np.mean(np.minimum(np.linalg.norm(points - old[0], axis=1), 1000)) < 5
                for old in candidates
            ):
                continue
            candidates.append((points, float(np.mean(support)), area))
    return sorted(candidates, key=lambda item: item[2], reverse=True)
