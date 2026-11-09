# Third-party dependencies

The dependency lock records exact installed package versions. The project uses:

| Component | Purpose | Upstream licensing reference |
|---|---|---|
| Ultralytics and YOLO11 pretrained weights | Person/phone detection and pose | https://www.ultralytics.com/license |
| PyTorch / TorchVision | Model runtime | https://github.com/pytorch/pytorch/blob/main/LICENSE |
| OpenCV Python | Image transformations and annotation | https://github.com/opencv/opencv-python/blob/master/LICENSE.txt |
| PyAV | Timestamp-aware video decoding | https://github.com/PyAV-Org/PyAV/blob/main/LICENSE.txt |
| FFmpeg libraries bundled by video wheels | Codec support | https://ffmpeg.org/legal.html |
| Streamlit | Local browser UI | https://github.com/streamlit/streamlit/blob/develop/LICENSE |
| NumPy | Numerical operations | https://numpy.org/doc/stable/license.html |
| RapidOCR / bundled PaddleOCR models | Local screen text detection and recognition | https://github.com/RapidAI/RapidOCR ; https://github.com/PaddlePaddle/PaddleOCR |
| ONNX Runtime | Local CPU OCR inference | https://github.com/microsoft/onnxruntime/blob/main/LICENSE |
| ReportLab | Local PDF layout and embedded evidence | https://www.reportlab.com/opensource/ |
| pypdf | Development PDF text and image checks | https://github.com/py-pdf/pypdf/blob/main/LICENSE |
| pytest | Development tests | https://github.com/pytest-dev/pytest/blob/main/LICENSE |

These links are attribution/navigation aids, not a complete legal inventory.
Native wheel codec features and transitive dependencies have their own notices.
There is no policy in this standalone project to exclude GPL/LGPL components.
