# ScreenProctor POC

A standalone local Python project for analyzing uploaded videos and reviewing
timestamped evidence of additional people, phone presence/interaction/placement,
AI interfaces, and screen changes. It does not depend on the CV-CUE repository or the colleague's project.

Version 0.4.4 detects low-contrast text/layout transitions between pale pages,
checks that a candidate view itself remains stable, and records capture times
on before/after screenshots. The before image now follows the latest comparable
unchanged view. Existing reports need **Analyze video** again to gain missed
events; regenerating a PDF alone does not rerun detection. Live PDF exports refresh
the renderer without restarting the browser server. Phone detection is unchanged.

Version 0.4.3 adds self-contained PDF reports with embedded screenshots, readable
coverage and unassessed intervals, and grouped phone-placement/possible-use incidents.
Visual changes remain separate from verified application transitions. That reporting release retained detection
engine 0.4.2 and phone thresholds. Existing reports can be exported
without reanalyzing the video.

Version 0.4.2 labels visual changes as **Screen change** and uses the estimated
transition window as the primary review time. The later confirmation time is
listed separately. Existing observation timestamps remain available in details.

Version 0.4.1 makes screen changes prominent in the UI and JSON summary, opens
the latest before/after comparison first, and writes a local `review.html` in each
new analysis directory. Existing 0.4 reports render with the improved UI without
reanalysis. Screen-change detection works independently of app identification.

Engine 0.4 adds outer-display boundary detection and explicit comparison recovery
after tracking gaps. It retains hands-free phone-placement risk and periodic local
OCR recognition of AI interfaces.
See [FIX_NOTES.md](FIX_NOTES.md) for the latest reference-video results, remaining
misses, and the differences from the original baseline in `VALIDATION.md`.

## Setup and start

See [SETUP.md](SETUP.md) for prerequisites, fresh-clone setup, manual Windows
instructions, Git sharing, updates and troubleshooting. Python 3.12 is recommended;
Python 3.11–3.13 is supported by the package. Development was validated on macOS
with Apple Silicon.

For this existing local copy:

```bash
cd ~/Documents/ScreenProctorPOC
bash setup.sh
bash run.sh
```

For a fresh clone, replace the repository URL before running:

```bash
git clone 'REPLACE_WITH_REPOSITORY_URL' ScreenProctorPOC
cd ScreenProctorPOC
bash setup.sh
bash run.sh
```

Setup installs dependencies, downloads the three YOLO models and runs the tests.
Open the localhost URL printed in the terminal, normally http://localhost:8501.
Upload a video, select its recording type, run **Analyze video**, then choose
**Download PDF report with screenshots**. Processing uses local models; no cloud
API key is required. Git stores the source; it does not host the application.

Models, recordings, generated reports, local validation artifacts and backups are
excluded from Git. Recreate synthetic demos with the commands in SETUP.md.
`requirements.lock` records the macOS development environment; other platforms
may need independently resolved dependencies and validation.

## What each result means

| Event | Evidence | Interpretation |
|---|---|---|
| `additional_person_candidate` | At least two detected bodies in the camera region over time | Multiple person detections; exclude reflections/displayed images during review |
| `ambiguous_person_candidate` | Low-contrast person-like silhouette | Not counted as verified additional-person evidence; review for reflections or distant people |
| `phone_present` | A COCO phone detection persists | A phone is visible, including one untouched on a desk |
| `possible_phone_interaction` | A confidently estimated wrist remains near a phone | Possible handling; operation is unverified |
| `phone_positioned_for_viewing` | Model-confirmed portrait phone overlapping the upper laptop area | Hands-free viewing risk; no wrist required |
| `phone_placement_candidate` | Dark portrait obstruction in the upper laptop area | Phone-shaped geometry only; verify identity in evidence |
| `possible_phone_use` | Hand/head/movement evidence OR placement risk | Possible use, including hands-free viewing; not proof of operation |
| `ai_interface_visible` | Readable known-service header/domain plus a separate chat control | Interface visibility; active assistance is unverified |
| `ai_interface_candidate` | Explicit generic AI-assistant header plus chat control | Unidentified assistant-like interface; review required |
| `screen_content_changed` | A substantially changed display settles into a new view | Layout/content changed; application identity can remain unidentified even when the change is clear |
| `screen_comparison_reset` | A long tracking gap or incompatible display region prevents comparison | Unassessed interval; this is not an observed screen switch |
| `page_hidden`, `window_blur`, `fullscreen_exit` | Optional recorded client telemetry | Browser visibility/focus events, not a destination-app identification |
| `foreground_app_changed` | Optional externally collected foreground-app event | Recorded application transition; validate source and time alignment |

Report scores are detector scores or heuristic evidence scores, not calibrated
probabilities of cheating. The system never automatically issues a misconduct
verdict or identifies someone biometrically.

## Recording modes

* **External camera:** detects people and phones across the full camera view.
  Screen analysis prefers outer-display quadrilaterals supported by long image
  edges inside detected laptops, then tracks their borders using optical flow/RANSAC.
  Text-bearing regions are a fallback; a pane-sized reacquisition is rejected
  when it conflicts with the previous display region.
  The report shows the selected display and before/after crops for each change.
  Optional manual corners override automatic localization. Enter them as
  top-left, top-right, bottom-right, bottom-left, for example
  `0.40,0.30; 0.70,0.32; 0.68,0.70; 0.35,0.67`.
  This is an example, not calibration for your video.
* **Webcam:** camera observations only. Screen switching is marked not assessable.
* **Screen:** visual screen transitions and periodic AI-interface checks. Physical people and phones are
  marked not assessable; pictures of people/devices on the desktop are not
  counted as physical observations.
* **Combined:** requires explicit non-overlapping camera and screen crop regions
  in normalized `x,y,width,height`. Crop the screen to exclude a camera overlay.
  The example configuration is for an illustrative side-by-side layout only.

Automatic localization reacquires after detected camera cuts. Short gaps retain
the last comparable baseline for up to five seconds, breaking all dwell support
during the gap. A stable changed view after recovery can still produce a change
event, with an uncertain onset and a recorded comparison gap. Longer gaps and
incompatible regions produce an explicit `screen_comparison_reset` rather than
silently adopting a new baseline. Reports list unavailable intervals in
`screen_localization.tracking_gaps`; the UI displays them separately. Manual calibration
still requires a fixed shot: it is invalidated after a detected cut. Select a
time range for each manually calibrated shot. Person/phone analysis continues
with new local track IDs. Combined layouts must remain fixed; use
separate runs if their panels move. This avoids pretending that arbitrary video
contains enough information to verify every requirement.

Screen corner order, geometry and region bounds are validated. Perspective
correction improves comparison; it cannot restore text/detail absent from the
source. Screen transitions do not establish application/tab identity. AI recognition
separately matches readable known-service headers and chat controls. It does not
identify every arbitrary application.

## CLI

```bash
.venv/bin/screenproctor analyze \
  --input '/path/to/video.mp4' \
  --output runs/my-first-analysis \
  --mode external --fps 4

.venv/bin/screenproctor analyze \
  --input '/path/to/combined.mp4' \
  --output runs/combined-analysis \
  --config examples/combined.json
```

Output must be a **new directory**. Existing files are preserved. Container
support comes from PyAV/FFmpeg; the UI accepts MP4, AVI, MOV, MKV, WebM and M4V.
The CLI attempts any decodable video rather than trusting its extension.

Configuration accepts `mode`, `fps`, `threshold`, `minimum`, `camera_roi`,
`screen_roi`, `screen_corners`, `ignore_regions`, `start_seconds`, `end_seconds`,
`auto_screen`, `phone_placement`, `ai_scan` (all true by default), and
`ai_interval` (1 second by default; 0.5–5 seconds). Set the last three in JSON or
use the corresponding UI controls. AI checks run on scheduled sampled frames,
independently of screen transitions and white text-area localization; at low
sample FPS the effective scan frequency cannot exceed sampling frequency.
The optional time range selects a single calibrated shot without copying or
editing the input video. Report timestamps remain relative to the original video.
Optional ignore regions are
normalized `x,y,width,height` boxes inside the camera crop, for known mirrors,
posters, or displayed images. They are explicitly excluded from analysis; do not
mask an area that needs monitoring. Add calibrated corners to the external JSON
when appropriate:

```json
{
  "mode": "external",
  "fps": 4,
  "screen_corners": [[0.40,0.30],[0.70,0.32],[0.68,0.70],[0.35,0.67]]
}
```

Model preparation is explicit:

```bash
.venv/bin/screenproctor prepare-models --models models
```

The models are YOLO11m (full-frame detection), YOLO11n (crop corroboration), and
YOLO11n-pose. Phone alerts require spatial agreement and a score of at least 0.55
in full-frame and crop predictions, independently of a lower general threshold.
Placement candidates use a separate portrait-geometry path, with explicit object
identity uncertainty; confirmed-phone thresholds remain unchanged.
This precision-oriented rule can miss small, stationary, or partly hidden phones.

The manifest records downloaded model checksums and is checked before loading
models. It detects subsequent local changes; it is not an independent signature
of the original upstream release. Download models only from a trusted source.

## Review outputs

Each new run contains **`report.pdf`**, `review.html`, `report.json` and an `evidence/`
directory. The PDF embeds annotated camera images and before/after screen screenshots,
so it can be read independently of the project. Use **Download PDF report with
screenshots** in the UI. Existing analysis results also support this download on rerun;
video reanalysis is unnecessary. JSON remains an optional technical export.

Convert a saved JSON report with local evidence:

```bash
.venv/bin/screenproctor export-pdf \
  --report '/path/to/run/report.json' \
  --output '/path/to/new-report.pdf'
```

If the JSON has been downloaded elsewhere, add `--evidence-root /path/to/original/run`.
That directory must contain `evidence/`. A JSON file alone does not contain screenshots;
missing/invalid images are marked unavailable in the PDF. Exports preserve existing files.

`incident_summary` groups exact matching placement/derived-use pairs while retaining raw
`events`. Counts are grouped observations, not counts of misconduct or distinct devices.
`coverage_summary` makes screen-localization gaps explicit. The readable summary uses
estimated transition windows; raw screen-event `start_seconds`/`end_seconds` retain
stable-observation timing for compatibility. `confirmed_at_seconds` is separate.
`review_metadata` records report format 0.4.4 independently of the detection-engine version.

See [VALIDATION_PLAN.md](VALIDATION_PLAN.md) for held-out session evaluation and metrics.
The included reference video and synthetic tests do not establish general accuracy.

Per-capability assessments distinguish `candidate_detected`, `no_event_observed`, and
`not_assessable`. The coverage fraction records usable sampled frames. AI coverage
uses readable scheduled OCR scans as its denominator instead, and records both
scan counts. Unreadable text or OCR failure results in `not_assessable`, not a
claim that no AI interface was present. The report and UI show the area inspected
by AI checks, including the latest scan when no interface could be recognized.
Each screen-change event also includes an `ai_interface_check` with nearby scan
coverage and any related sustained AI-interface observations. This association
does not identify the destination app or establish active AI assistance. For
phone interaction, it requires at least one visible wrist; this is a coarse
coverage indicator, not a guarantee that every hand action was observable.
Assessments without an event require at least 60% usable samples before they
are marked `no_event_observed`. Hidden objects can still be missed.

Events require elapsed observed support, not just a fixed number of frames.
Short gaps can be bridged but do not count as positive support. Event bounds
are the first/last positive sampled timestamps; they do not imply exact physical
onset/offset. Actual source presentation timestamps are used, including VFR
recordings. Screen changes use a separate temporal state so oscillating subtype
labels cannot erase a continuous anomaly. Successive stable views update the
screen anchor, so A → B → C does not require returning to A.

Sampling defaults to 4 FPS and can be raised for short events. Decoding and
inference are sequential, with overlapping phone crops; processing may be slower
than playback on CPU. Input videos are never modified. Browser uploads remain
under `runs/`; delete those directories when no longer needed.

## AI recognition and limitations

Local RapidOCR/ONNX recognition checks the whole detected laptop box in external
mode, the supplied screen region in combined/screen mode, or manual corners as a
fallback when no laptop is detected. It does not depend on a screen-change event
or the automatic display quad. Known headers include ChatGPT, Claude, Gemini,
Copilot, Perplexity and DeepSeek; a separate chat control must also be readable.
Brand mentions inside email/document text are insufficient. Reports retain only
allowlisted matched cues, not raw OCR text or extracted prompts. Evidence images
still contain the original visible screen, so handle them as session data.

This is a heuristic recognizer, not proof of actual AI assistance. Unknown
services, tiny or blurred text, non-English controls and mimicked interfaces
remain limitations. The original reference video's later dark panel now produces a visual screen-change
event, but its application is **not reliably identifiable**. A direct screen recording
or readable browser telemetry is needed to resolve that case.

A generated static AI-interface demo exercises recognition with no transitions:

```bash
.venv/bin/python tools/create_ai_demo.py
.venv/bin/screenproctor analyze --input examples/demo_ai_static.mp4 \
  --output runs/static-ai-demo --mode screen
```

The demo is a synthetic test fixture, not an actual ChatGPT session.
Regenerate it using `.venv/bin/python tools/create_ai_demo.py`.

## Optional screen telemetry

`tools/browser-telemetry.js` is an example collector for an exam page you control.
Start it at the same session origin as the video and export
`window.proctorTelemetry.export()`. Adjust event times to recording-relative
seconds if the origins differ. This project does not inject the script into
other websites and cannot recover telemetry from an existing video.

```bash
.venv/bin/screenproctor analyze --input session.mp4 \
  --output runs/with-telemetry --mode webcam \
  --telemetry session-events.json
```

Telemetry must have recording-relative `time_seconds` and an allowed `type`.
The sample telemetry is illustrative; never attach it as evidence for a real clip.
Focus loss cannot establish which application opened. Native foreground-app
collection is an integration point, not an implemented recorder in this POC.

## Validation and further work

```bash
.venv/bin/python -m pytest -q
```

Tests cover split dark/bright displays, pane-sized reacquisition rejection,
short/long tracking gaps, incompatible crops, AI context attached to screen changes,
event persistence/gaps, people and phone report generation, stationary
phones, proximity versus possible use, scene boundaries, invalid calibration,
successive screen views, VFR timestamps, corrupt input, and output preservation.
See `FIX_NOTES.md` for the current reference-video results and `VALIDATION.md`
for the historical baseline checks.

A self-generated screen demo changes views at 5s and 10s. Generate it after cloning:

```bash
.venv/bin/python tools/make_demo.py
.venv/bin/screenproctor analyze --input examples/demo_screen.mp4 \
  --output runs/screen-demo --mode screen
```

This is a POC, not an accuracy-certified product. Small/occluded phones, partial
bodies, reflections, people shown on physical monitors, poor lighting, inaccurate
pose estimates, and camera motion can cause errors. Two-person counting does not
detect substitution when only one person is visible. Stationary phone use away
from the head can appear only as interaction or be missed. The phone-to-person
association is spatial and can be ambiguous in a crowd. The local IoU tracker
can switch IDs under occlusion. Stable scrolling, notifications, theme changes,
or resizing can look like screen transitions; visually similar switches may be
missed. Audio is not analyzed. Rotation stored only in unsupported container
side-data may require transcoding to an upright video first.

Before claiming reliability, annotate unseen sessions and report event precision,
recall, false alerts per hour, coverage, and processing time separately by mode.
Split evaluation by participant/session. Use failures to tune thresholds or
fine-tune a detector/action model, rather than optimizing on this one clip.

## Third-party components

See `THIRD_PARTY.md`. This project uses Ultralytics YOLO models/software; review
their AGPL-3.0 / commercial licensing terms before choosing a distribution model.
