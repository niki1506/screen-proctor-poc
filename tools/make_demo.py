"""Create a small screen-only demo with transitions at 5s and 10s."""

import sys
from pathlib import Path

import av
import cv2
import numpy as np


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/demo_screen.mp4")
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=4)
        stream.width = 960
        stream.height = 600
        stream.pix_fmt = "yuv420p"
        for n in range(60):
            section = n // 20
            colors = [(40, 40, 40), (230, 225, 215), (90, 40, 20)]
            image = np.full((600, 960, 3), colors[section], np.uint8)
            cv2.rectangle(
                image,
                (0, 0),
                (960, 80),
                [(80, 50, 20), (140, 60, 100), (40, 120, 50)][section],
                -1,
            )
            titles = [
                "EXAM - coding exercise",
                "REFERENCE - documentation",
                "WORKSPACE - another application",
            ]
            cv2.putText(
                image,
                titles[section],
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                (255, 255, 255),
                2,
            )
            for row in range(7):
                cv2.putText(
                    image,
                    f"Sample content row {row + 1}, view {section + 1}",
                    (40, 140 + row * 55),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (150, 160, 170),
                    2,
                )
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    print(path)


if __name__ == "__main__":
    main()
