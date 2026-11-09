"""Create a readable, synthetic static AI interface for pipeline smoke checks."""

from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np


def create(path):
    image = np.full((720, 1280, 3), 235, np.uint8)
    for text, x, y in [
        ("ChatGPT", 40, 70),
        ("Synthetic test interface", 650, 70),
        ("New chat", 40, 180),
        ("How can I help you?", 350, 340),
        ("Message ChatGPT", 300, 600),
        ("Send", 1090, 600),
    ]:
        cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 20), 2)
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=4)
        stream.width, stream.height = 1280, 720
        stream.pix_fmt = "yuv420p"
        for n in range(24):
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = n, Fraction(1, 4)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


if __name__ == "__main__":
    create(Path(__file__).resolve().parents[1] / "examples" / "demo_ai_static.mp4")
