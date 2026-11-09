"""Conservative, reviewable phone-placement geometry; no hand contact required."""

import cv2
import numpy as np

from .vision import Object, iou


def phone_shaped_obstructions(image, laptops):
    """Find dark portrait rectangles in the upper laptop area.

    Geometry cannot prove object identity. These candidates must be reported as
    uncertain obstructions, separately from model-confirmed phones. Multiple
    thresholds handle glass reflections without weakening object thresholds.
    """
    height, width = image.shape[:2]
    found = []
    for laptop in laptops:
        x, y, r, b = map(int, laptop.box)
        x, y = max(0, x), max(0, y)
        r, b = min(width, r), min(height, b)
        bottom = round(y + (b - y) * 0.78)
        region = image[y:bottom, x:r]
        if min(region.shape[:2], default=0) < 50:
            continue
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        for threshold in (45, 55, 60, 65):
            dark = np.uint8(gray < threshold) * 255
            dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                rect = cv2.minAreaRect(contour)
                short, long = sorted(rect[1])
                if short < 12 or not 1.65 < long / short < 3.1:
                    continue
                area = short * long
                if not 0.025 < area / max(1, (r - x) * (b - y)) < 0.20:
                    continue
                if cv2.contourArea(contour) / area < 0.60:
                    continue
                left, top, w, h = cv2.boundingRect(contour)
                if h < 1.25 * w or h < 0.30 * (b - y) or top < 2:
                    continue
                # Exclude clipped bezel/background components and keyboard keys.
                if left < 2 or left + w >= r - x - 2 or top + h >= bottom - y - 2:
                    continue
                mask = np.zeros_like(gray)
                cv2.drawContours(mask, [contour], -1, 255, -1)
                mask = cv2.erode(mask, np.ones((7, 7), np.uint8))
                values = gray[mask > 0]
                if len(values) < 100 or np.std(values) > 22 or np.mean(values) > 65:
                    continue
                obj = Object(
                    "phone_placement_candidate",
                    (x + left, y + top, x + left + w, y + top + h),
                    0.6,
                )
                if not any(iou(obj.box, old.box) > 0.4 for old in found):
                    found.append(obj)
    return found


def positioned_phones(phones, laptops):
    """Confirmed portrait phone overlapping the upper laptop area."""
    found = []
    for phone in phones:
        x, y, r, b = phone.box
        if b - y < 1.25 * (r - x):
            continue
        for laptop in laptops:
            lx, ly, lr, lb = laptop.box
            intersection = max(0, min(r, lr) - max(x, lx)) * max(
                0, min(b, ly + 0.78 * (lb - ly)) - max(y, ly)
            )
            if intersection / max(1, (r - x) * (b - y)) >= 0.65:
                found.append(phone)
                break
    return found
