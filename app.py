"""Local browser UI. Every analysis runs in a separate process."""

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from importlib import reload

import cv2
import streamlit as st

from screenproctor.video import frames
from screenproctor import review

# Streamlit may rerun app.py while retaining an older imported helper module.
# Review helpers are stateless, so refresh them without restarting user sessions.
review = reload(review)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="ScreenProctor POC", layout="wide")
st.title("ScreenProctor")
st.caption("Analysis engine 0.4.4 · PDF reports 0.4.4 · screen changes and evidence")
st.write(
    "Upload a recording to review phone placement/interaction, AI interfaces, additional people, and screen changes."
)
st.caption(
    "Results describe visible evidence. A phone on a desk is recorded as presence; application switching remains inferred unless supported by recorded client events."
)

upload = st.file_uploader("Video", type=["mp4", "avi", "mov", "mkv", "webm", "m4v"])
mode = st.selectbox(
    "Recording type",
    ["external", "webcam", "screen", "combined"],
    format_func=lambda value: {
        "external": "External camera showing the person and laptop",
        "webcam": "Webcam / camera only",
        "screen": "Screen recording only",
        "combined": "Separate screen and camera panels in one video",
    }[value],
)


def parse_region(value):
    return [float(v.strip()) for v in value.split(",")] if value.strip() else None


with st.expander(
    "Analysis settings and screen calibration",
    expanded=mode in {"external", "combined"},
):
    fps = st.slider("Samples per second", 1, 10, 4)
    threshold = st.slider("Object detection threshold", 0.1, 0.9, 0.35, 0.05)
    st.caption(
        "Confirmed phone detections require matching full-frame and crop predictions. Placement checks separately flag uncertain portrait objects against a laptop display; these do not require hand contact."
    )
    phone_placement = st.checkbox(
        "Flag phone placement near the laptop display",
        value=True,
        help="Allows hands-free viewing risk alerts. Geometry-only candidates need review to confirm object identity.",
    )
    ai_scan = st.checkbox(
        "Check for visible AI interfaces",
        value=True,
        help="Local OCR runs independently of screen changes and examines the whole laptop area. Unreadable text remains not assessable.",
    )
    ai_interval = st.slider("AI scan interval in seconds", 0.5, 5.0, 1.0, 0.5)
    minimum = st.slider("Minimum event support in seconds", 0.25, 3.0, 0.75, 0.25)
    start_seconds = st.number_input(
        "Analyze from second", min_value=0.0, value=0.0, step=1.0
    )
    until_seconds = st.number_input(
        "Analyze until second (0 = end)", min_value=0.0, value=0.0, step=1.0
    )
    ignore_text = st.text_input(
        "Optional regions to exclude inside the camera view",
        placeholder="x,y,width,height; x,y,width,height",
    )
    st.caption(
        "Use exclusions for known mirrors, posters, or displayed video. Coordinates are relative to the camera crop. Excluded areas will not be analyzed."
    )
    camera_text = ""
    screen_text = ""
    corners_text = ""
    auto_screen = True
    if mode == "combined":
        st.write(
            "Enter non-overlapping camera and screen regions as x, y, width, height, each normalized to 0–1. Crop the screen to exclude the camera panel."
        )
        camera_text = st.text_input("Camera region", placeholder="0.8, 0, 0.2, 1")
        screen_text = st.text_input("Screen region", placeholder="0, 0, 0.8, 1")
    if mode == "external":
        auto_screen = st.checkbox(
            "Automatically locate and track the laptop display", value=True
        )
        st.write(
            "Screen analysis runs automatically when a text-bearing laptop display can be located. Optional corners override automatic localization for a fixed shot; enter top-left, top-right, bottom-right, bottom-left. The report shows the display region and before/after evidence."
        )
        corners_text = st.text_input(
            "Normalized screen corners",
            placeholder="0.40,0.30; 0.70,0.32; 0.68,0.70; 0.35,0.67",
        )
    preview_seconds = st.number_input(
        "Preview at video second", min_value=0.0, value=0.0, step=1.0
    )
    telemetry = st.file_uploader("Optional synchronized telemetry JSON", type=["json"])

if upload:
    digest = hashlib.sha256(upload.getbuffer()).hexdigest()
    if st.session_state.get("upload_key") != digest:
        job = ROOT / "runs" / uuid.uuid4().hex
        job.mkdir(parents=True)
        source = job / ("input" + Path(upload.name).suffix.lower())
        source.write_bytes(upload.getbuffer())
        st.session_state.update(upload_key=digest, source=str(source), job=str(job))
        st.session_state.pop("report_path", None)
    source = Path(st.session_state["source"])
    st.video(str(source))
    if st.button("Show calibration preview"):
        try:
            preview = None
            for seconds, image in frames(source, 1):
                preview = image
                if seconds >= preview_seconds:
                    break
            if preview is None:
                raise ValueError("No preview frame decoded")
            h, w = preview.shape[:2]
            for fraction in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
                cv2.line(
                    preview,
                    (round(w * fraction), 0),
                    (round(w * fraction), h),
                    (120, 120, 120),
                    1,
                )
                cv2.line(
                    preview,
                    (0, round(h * fraction)),
                    (w, round(h * fraction)),
                    (120, 120, 120),
                    1,
                )
                cv2.putText(
                    preview,
                    str(fraction),
                    (round(w * fraction), 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 200, 255),
                    1,
                )
                cv2.putText(
                    preview,
                    str(fraction),
                    (0, round(h * fraction)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 200, 255),
                    1,
                )
            st.image(
                cv2.cvtColor(preview, cv2.COLOR_BGR2RGB),
                caption="Coordinates: x increases rightward; y increases downward.",
            )
        except Exception as error:
            st.error(str(error))
    if st.button("Analyze video", type="primary"):
        try:
            config = {
                "auto_screen": auto_screen,
                "phone_placement": phone_placement,
                "ai_scan": ai_scan,
                "ai_interval": ai_interval,
                "mode": mode,
                "fps": fps,
                "threshold": threshold,
                "minimum": minimum,
                "start_seconds": start_seconds,
                "end_seconds": until_seconds or None,
                "camera_roi": parse_region(camera_text),
                "screen_roi": parse_region(screen_text),
                "ignore_regions": [parse_region(p) for p in ignore_text.split(";")]
                if ignore_text.strip()
                else None,
                "screen_corners": [parse_region(p) for p in corners_text.split(";")]
                if corners_text.strip()
                else None,
            }
            run = Path(st.session_state["job"]) / uuid.uuid4().hex
            configuration = run.with_suffix(".json")
            configuration.write_text(json.dumps(config))
            command = [
                sys.executable,
                "-m",
                "screenproctor.cli",
                "analyze",
                "--input",
                str(source),
                "--output",
                str(run),
                "--models",
                str(ROOT / "models"),
                "--config",
                str(configuration),
            ]
            if telemetry:
                path = run.with_suffix(".telemetry.json")
                path.write_bytes(telemetry.getbuffer())
                command += ["--telemetry", str(path)]
            with st.status("Analyzing the recording…", expanded=True) as status:
                message = st.empty()
                with (run.with_suffix(".log")).open("w+") as errors:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=errors,
                        text=True,
                        cwd=ROOT,
                    )
                    for line in process.stdout:
                        try:
                            event = json.loads(line)
                            if "processed_seconds" in event:
                                message.write(
                                    f"Processed {event['processed_seconds']:.1f} seconds"
                                )
                        except json.JSONDecodeError:
                            pass
                    if process.wait() != 0:
                        errors.seek(0)
                        raise RuntimeError(errors.read()[-2000:])
                status.update(label="Analysis complete", state="complete")
            st.session_state["report_path"] = str(run / "report.json")
        except Exception as error:
            st.error(str(error))

if st.session_state.get("report_path"):
    path = Path(st.session_state["report_path"])
    report = json.loads(path.read_text())
    if report.get("analysis_version") not in {"0.4.0", "0.4.1", "0.4.2", "0.4.4"}:
        st.warning(
            "This report was produced by the earlier detector. Run Analyze video again to use the updated engine; saved reports are preserved."
        )
    if report.get("analysis_version") in {"0.4.0", "0.4.1", "0.4.2"}:
        st.info(
            "Low-contrast screen-change detection has been updated. Run Analyze video again to detect earlier missed changes; downloading an existing report only refreshes its presentation."
        )
    report = review.review_report(report)
    changes = sorted(
        [
            event
            for event in report["events"]
            if event["type"] == "screen_content_changed"
        ],
        key=lambda event: event["start_seconds"],
        reverse=True,
    )
    if changes:
        st.success(review.screen_change_summary(report)["message"])
        st.subheader("Screen changes detected")
        st.caption(
            "Visual changes are observations requiring review; they do not confirm application switches. Times show estimated transitions, with confirmation listed separately."
        )
        for index, event in enumerate(changes):
            timing = review.screen_change_timing(event)
            with st.expander(
                f"{timing['start_seconds']:.3f}–{timing['end_seconds']:.3f}s · Screen change",
                expanded=index == 0,
            ):
                if "before_screenshot" in event and "after_screenshot" in event:
                    left, right = st.columns(2)
                    left.image(
                        str(path.parent / event["before_screenshot"]),
                        caption=f"Before at {event['before_timestamp_seconds']:.3f}s"
                        if "before_timestamp_seconds" in event
                        else "Before",
                    )
                    right.image(
                        str(path.parent / event["after_screenshot"]),
                        caption=f"After at {event['after_timestamp_seconds']:.3f}s"
                        if "after_timestamp_seconds" in event
                        else "After",
                    )
                elif "screenshot" in event:
                    st.image(str(path.parent / event["screenshot"]))
                st.write(
                    f"Timing: {timing['timing_basis'].replace('_', ' ')}. Confirmed at {timing['confirmed_at_seconds']:.3f}s."
                )
                with st.expander("Observation details"):
                    st.write(event.get("reason", ""))
                    st.json(event)
    coverage = report["coverage_summary"]
    gaps = coverage["unassessed_screen_intervals"]
    if gaps:
        intervals = "; ".join(
            f"{gap['start_seconds']:.3f}–{gap['end_seconds']:.3f}s"
            if gap["end_seconds"] is not None
            else f"from {gap['start_seconds']:.3f}s"
            for gap in gaps
        )
        st.warning(
            f"Screen unassessed: {intervals}. Changes during these intervals cannot be excluded."
        )
    st.subheader("Assessment")
    st.dataframe(coverage["capabilities"], hide_index=True)
    st.caption(coverage["note"])
    ai = report["assessments"].get("ai_interface", {})
    if ai.get("result") == "not_assessable":
        with st.expander("Application identification details"):
            st.write(
                "The application name could not be established from readable text. Screen-change alerts above remain valid visual observations."
            )
            st.json(ai)
    st.caption(
        "Phone-use risk includes hands-free placement. AI-interface visibility and phone placement are review signals; active use is unverified."
    )
    inspection = report.get("ai_inspection", {})
    if inspection.get("latest_preview"):
        with st.expander("Area checked for AI interfaces"):
            st.image(
                str(path.parent / inspection["latest_preview"]),
                caption=f"Latest periodic AI check at {inspection['latest_scan_seconds']:.2f}s. Whole laptop area is checked independently of display tracking.",
            )
    display = report.get("screen_localization", {})
    if display.get("preview"):
        with st.expander("Display region analyzed", expanded=False):
            st.image(
                str(path.parent / display["location_preview"]),
                caption="Located display boundary",
            )
            st.image(
                str(path.parent / display["preview"]),
                caption="Rectified display preview",
            )
    elif mode == "external":
        st.warning(
            "No usable display was localized. Screen changes remain unassessed; use optional corners or provide a direct screen recording."
        )
    if display.get("tracking_gaps"):
        with st.expander("Intervals when the screen could not be assessed"):
            st.dataframe(display["tracking_gaps"], hide_index=True)
            st.caption(
                "Changes across short gaps have uncertain timing. Longer gaps or a changed display region reset comparison and are reported explicitly."
            )
    incidents = [
        item
        for item in report["incident_summary"]["incidents"]
        if item["type"] != "screen_content_changed"
    ]
    st.subheader(f"Other observations ({len(incidents)})")
    if not report["events"]:
        st.info(
            "No events met the configured thresholds. Check assessment coverage before interpreting this result."
        )
    for incident in incidents:
        with st.expander(
            f"{incident['start_seconds']:.2f}–{incident['end_seconds']:.2f}s · {incident['title']}"
        ):
            st.write(incident["reason"])
            if len(incident["labels"]) > 1:
                st.caption(
                    "One incident with phone-placement and possible-use labels. Active operation is unverified."
                )
            image = review.evidence_path(path.parent, incident.get("screenshot"))
            if image:
                st.image(str(image))
            with st.expander("Technical observation details"):
                st.json([report["events"][i] for i in incident["event_indices"]])
    st.caption(review.VALIDATION_NOTE)
    try:
        st.download_button(
            "Download PDF report with screenshots",
            review.pdf_report_bytes(report, path.parent),
            "report.pdf",
            "application/pdf",
            type="primary",
        )
    except Exception as error:
        st.error(f"PDF export failed: {error}")
    st.download_button(
        "Download JSON report",
        json.dumps(
            review.review_report(report), indent=2, ensure_ascii=False, allow_nan=False
        ).encode("utf8"),
        "report.json",
        "application/json",
    )
    with st.expander("Coverage and limitations"):
        st.json(
            {"diagnostics": report["diagnostics"], "limitations": report["limitations"]}
        )
