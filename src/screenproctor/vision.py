"""Local COCO detection and pose association. No biometric identification."""

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Object:
    label: str
    box: tuple
    score: float
    points: dict | None = None


def confirmed_phones(predictions, tiled, threshold=0.55):
    """Require a phone in the full view and corroborating spatial evidence.

    Crop-only detections cannot establish an object class. This deliberately
    favors precision and may miss small/occluded phones.
    """
    accepted = []
    for obj, view in predictions:
        if obj.label != "phone" or view != 0 or obj.score < threshold:
            continue
        support = [
            p
            for p, v in predictions
            if v != 0
            and p.label == "phone"
            and p.score >= threshold
            and iou(p.box, obj.box) >= 0.4
        ]
        if (tiled and support) or (not tiled and obj.score >= max(0.65, threshold)):
            accepted.append(obj)
    return accepted


def clear_person(image, person):
    """Low-contrast silhouettes remain ambiguous, rather than confirmed people."""
    x, y, r, b = map(int, person.box)
    patch = image[
        max(0, y) : min(image.shape[0], b), max(0, x) : min(image.shape[1], r)
    ]
    if patch.size == 0:
        return False
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return bool(np.percentile(gray, 90) - np.percentile(gray, 10) >= 30)


def iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    total = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / total if total else 0.0


class Detector:
    def __init__(self, directory, threshold=0.35):
        os.environ.setdefault(
            "YOLO_CONFIG_DIR",
            str(Path(directory).resolve().parent / ".cache" / "ultralytics"),
        )
        from ultralytics import YOLO, settings

        settings.update({"sync": False})

        directory = Path(directory)
        missing = [
            name
            for name in ("yolo11m.pt", "yolo11n.pt", "yolo11n-pose.pt")
            if not (directory / name).is_file()
        ]
        if missing:
            raise ValueError("Models missing. Run: screenproctor prepare-models")
        manifest = directory / "checksums.json"
        if not manifest.is_file():
            raise ValueError(
                "Model checksum manifest missing. Run prepare-models first."
            )
        checksums = json.loads(manifest.read_text())
        for name in ("yolo11m.pt", "yolo11n.pt", "yolo11n-pose.pt"):
            if (
                checksums.get(name)
                != hashlib.sha256((directory / name).read_bytes()).hexdigest()
            ):
                raise ValueError(f"Model checksum mismatch: {name}")
        self.objects = YOLO(str(directory / "yolo11m.pt"))
        self.tiles = YOLO(str(directory / "yolo11n.pt"))
        self.pose = YOLO(str(directory / "yolo11n-pose.pt"))
        self.threshold = threshold

    def predict(self, image):
        height, width = image.shape[:2]
        predictions = []
        # Full image plus overlapping quadrants retain small phones at higher resolution.
        views = [(0, 0, width, height)]
        if min(height, width) >= 480:
            w, h = round(width * 0.65), round(height * 0.65)
            views += [
                (x, y, x + w, y + h) for x in (0, width - w) for y in (0, height - h)
            ]
        for n, (x, y, r, b) in enumerate(views):
            model = self.objects if n == 0 else self.tiles
            result = model.predict(
                image[y:b, x:r],
                conf=self.threshold,
                imgsz=960,
                classes=[0, 63, 67],
                verbose=False,
            )[0]
            for row in result.boxes.data.cpu().numpy():
                left, top, right, bottom, score, label = row
                if int(label) in (0, 63) and n != 0:
                    continue  # Count bodies only on full image, avoiding clipped tiled duplicates.
                predictions.append(
                    (
                        Object(
                            {0: "person", 63: "laptop", 67: "phone"}[int(label)],
                            (
                                float(left + x),
                                float(top + y),
                                float(right + x),
                                float(bottom + y),
                            ),
                            float(score),
                        ),
                        n,
                    )
                )
        objects = [obj for obj, view in predictions if obj.label != "phone"]
        objects += confirmed_phones(
            predictions, len(views) > 1, max(0.55, self.threshold)
        )
        deduplicated = []
        for obj in sorted(objects, key=lambda v: v.score, reverse=True):
            if not any(
                obj.label == old.label and iou(obj.box, old.box) > 0.4
                for old in deduplicated
            ):
                deduplicated.append(obj)
        people = [o for o in deduplicated if o.label == "person"]
        if people:
            poses = self.pose.predict(
                image, conf=self.threshold, imgsz=960, verbose=False
            )[0]
            if poses.keypoints is not None:
                for box, points in zip(
                    poses.boxes.xyxy.cpu().numpy(),
                    poses.keypoints.data.cpu().numpy(),
                    strict=True,
                ):
                    person = max(people, key=lambda p: iou(p.box, box))
                    if iou(person.box, box) > 0.3:
                        person.points = {
                            name: (float(points[k][0]), float(points[k][1]))
                            for name, k in [
                                ("nose", 0),
                                ("left_wrist", 9),
                                ("right_wrist", 10),
                            ]
                            if points[k][2] > 0.45
                        }
        return deduplicated


class Tracks:
    """Greedy spatial association for a POC; IDs are local to one continuous shot."""

    def __init__(self, timeout=1.0):
        self.timeout = timeout
        self.items = {}
        self.next_id = 1

    def update(self, objects, timestamp):
        self.items = {
            k: v for k, v in self.items.items() if timestamp - v[1] <= self.timeout
        }
        assigned = {}
        candidates = sorted(
            (
                (iou(obj.box, old.box), k, n)
                for n, obj in enumerate(objects)
                for k, (old, _) in self.items.items()
                if old.label == obj.label
            ),
            reverse=True,
        )
        used = set()
        for score, k, n in candidates:
            if score >= 0.25 and k not in used and n not in assigned:
                assigned[n] = k
                used.add(k)
        output = []
        for n, obj in enumerate(objects):
            k = assigned.get(n)
            if k is None:
                k = self.next_id
                self.next_id += 1
            previous = self.items.get(k)
            self.items[k] = (obj, timestamp)
            output.append((k, obj, previous))
        return output


def interaction(phone, person, previous_phone=None, previous_person=None):
    """Return observable interaction evidence, never a definitive use verdict."""
    points = person.points or {}
    wrists = [points[k] for k in ("left_wrist", "right_wrist") if k in points]
    if not wrists:
        return {"assessable": False, "contact": False, "use": False}
    x, y, r, b = phone.box
    center = ((x + r) / 2, (y + b) / 2)
    diagonal = math.hypot(person.box[2] - person.box[0], person.box[3] - person.box[1])
    radius = max(math.hypot(r - x, b - y) * 0.65, diagonal * 0.055)
    wrist = min(wrists, key=lambda p: math.dist(p, center))
    contact = math.dist(wrist, center) <= radius
    near_head = "nose" in points and math.dist(center, points["nose"]) < diagonal * 0.22
    coupled = False
    if previous_phone is not None and previous_person is not None:
        old_center = (
            (previous_phone.box[0] + previous_phone.box[2]) / 2,
            (previous_phone.box[1] + previous_phone.box[3]) / 2,
        )
        old_points = previous_person.points or {}
        for key in ("left_wrist", "right_wrist"):
            if key in points and key in old_points:

                def relative(point, body):
                    return (np.array(point) - np.array(body.box[:2])) / np.array(
                        [
                            max(1, body.box[2] - body.box[0]),
                            max(1, body.box[3] - body.box[1]),
                        ]
                    )

                dimensions = np.array(
                    [person.box[2] - person.box[0], person.box[3] - person.box[1]]
                )
                dp = (
                    relative(center, person) - relative(old_center, previous_person)
                ) * dimensions
                dw = (
                    relative(points[key], person)
                    - relative(old_points[key], previous_person)
                ) * dimensions
                if (
                    np.linalg.norm(dp) > diagonal * 0.008
                    and np.linalg.norm(dp - dw) < radius * 0.6
                ):
                    coupled = True
    return {
        "assessable": True,
        "contact": contact,
        "use": contact and (near_head or coupled),
        "near_head": near_head,
        "moves_with_hand": coupled,
    }


def annotate(image, objects):
    image = image.copy()
    for obj in objects:
        x, y, r, b = map(int, obj.box)
        color = (0, 180, 255) if obj.label == "phone" else (80, 220, 80)
        cv2.rectangle(image, (x, y), (r, b), color, 2)
        cv2.putText(
            image,
            f"{obj.label} {obj.score:.2f}",
            (x, max(20, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )
        for point in (obj.points or {}).values():
            cv2.circle(image, tuple(map(int, point)), 5, (255, 0, 200), -1)
    return image
