"""Decode source presentation timestamps, including variable-frame-rate video."""

import math
from pathlib import Path

import av
import cv2


def frames(path, sample_fps=4.0, max_width=1600):
    if not math.isfinite(sample_fps) or not 0.25 <= sample_fps <= 30:
        raise ValueError("Sample FPS must be between 0.25 and 30")
    path = Path(path)
    if not path.is_file():
        raise ValueError("Input video does not exist")
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError("Input has no video stream")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        start = None
        next_sample = 0.0
        last = -1.0
        for frame in container.decode(stream):
            if frame.time is None:
                raise ValueError("Video lacks usable presentation timestamps")
            if start is None:
                start = float(frame.time)
            timestamp = float(frame.time) - start
            if timestamp < last - 1e-5:
                raise ValueError("Video presentation timestamps are not monotonic")
            last = timestamp
            if timestamp + 1e-6 < next_sample:
                continue
            image = frame.to_ndarray(format="bgr24")
            rotation = int(float(stream.metadata.get("rotate", 0))) % 360
            if rotation in (90, 180, 270):
                image = cv2.rotate(
                    image,
                    {
                        90: cv2.ROTATE_90_CLOCKWISE,
                        180: cv2.ROTATE_180,
                        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
                    }[rotation],
                )
            if image.shape[1] > max_width:
                image = cv2.resize(
                    image,
                    (max_width, round(image.shape[0] * max_width / image.shape[1])),
                )
            yield timestamp, image
            next_sample = (math.floor(timestamp * sample_fps + 1e-6) + 1) / sample_fps


def crop(image, region):
    if region is None:
        return image
    if len(region) != 4 or any(not math.isfinite(v) for v in region):
        raise ValueError("A crop needs four finite normalized values: x,y,width,height")
    x, y, w, h = region
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError("Crop must be within the image")
    height, width = image.shape[:2]
    left, top = round(x * width), round(y * height)
    right, bottom = round((x + w) * width), round((y + h) * height)
    if right - left < 16 or bottom - top < 16:
        raise ValueError("Selected region is too small")
    return image[top:bottom, left:right]
