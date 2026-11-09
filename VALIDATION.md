Current detection engine: **0.4.4**. Report format: **0.4.4**.
See [the latest readable report](validation/reviewed-reference-v044/report.pdf)
and [VALIDATION_PLAN.md](VALIDATION_PLAN.md) for the pending held-out evaluation.
The latest suite has 87 passing tests, including embedded PDF evidence,
grouped incidents, unavailable intervals and existing-report export. Engine 0.4.4 adds low-contrast layout comparison and candidate stability checks.
Phone detection is unchanged. See FIX_NOTES.md for fresh full-video results.

Historical validation notes follow. They retain their original engine versions.

Historical engine: **0.4.0**. See [FIX_NOTES.md](FIX_NOTES.md) and
[the new reference report](validation/reviewed-reference-v04/report.json).
The baseline observations below are historical and do not describe the current engine.

# Validation performed

This project was implemented independently of the colleague's source. Validation
is a functional POC check, not a statistical accuracy benchmark.

## Automated checks

The suite exercises elapsed-time persistence, detection gaps, scene boundaries,
parallel events, multiple-person reporting, phone proximity versus stronger use
signals, camera-relative motion, successive screen transitions, perspective
geometry, excluded regions, timestamp preservation for variable-frame-rate input,
time-range selection, corrupt files, missing models, output preservation, optional
telemetry validation, and initial Streamlit UI rendering.

Run `.venv/bin/python -m pytest -q` to reproduce. The project also received Python
format/lint checks and shell syntax checks.

## Real inference on your reference video

Input: `Video_20260527_134642_890 (1).mp4`, approximately 31 seconds, 1280×720.
Processed at 4 FPS: 125 sampled frames, using YOLO11n object and pose models.
See [the saved report](validation/reference-final/report.json) and its evidence.

| Finding | Reported source time | Review |
|---|---|---|
| Additional-person candidate | 5.003–11.760 seconds | Evidence shows two people in the foreground |
| Additional-person candidate | 19.003–25.260 seconds | Evidence includes a faint background/reflected silhouette; this is not verified as another physical person |
| Phone presence | Several intervals | Some phone detections are correct; other boxes cover a small desk object and require rejection/review |
| Possible phone interaction | 21.507–25.503 seconds | The saved box is over a desk object near a wrist; this is not verified phone operation |
| Possible phone use | No qualifying event | Absence of this event does not rule out stationary or occluded use |
| Screen changes | Not assessable in this run | No physical display calibration was supplied |

The false or ambiguous candidates demonstrate why the report uses candidate
labels and screenshots. Exclusion regions can remove known reflections/posters
from a specific capture setup, but should not be used to claim general accuracy.
The baseline needs more annotated sessions and likely detector/action-model
improvements before operational use.

The scene-boundary heuristic found one boundary in this clip. It does not find
every cut. Use a manually selected fixed-shot time range for physical-screen
calibration when the clip contains several views. Person/phone tracking does not
establish identity across shots.

The input was read directly from Downloads and is not copied into this project.
Only output evidence and reports are included.

## Self-generated screen demo

`examples/demo_screen.mp4` changes views at 5s and 10s. The implementation returned:

* `screen_content_changed` at 5.25–6.00 seconds.
* `screen_content_changed` at 10.25–11.00 seconds.

See [the report](validation/screen-demo/report.json). These timings include the
intentional settling/persistence delay. The demo verifies transition mechanics;
it does not measure application-switch classification accuracy on real desktops.

## Environment observations

The exact installed dependency versions are in `requirements.lock`. PyAV and the
OpenCV wheel both emit duplicate AVFoundation class warnings on this Mac. File
decoding, inference and tests completed successfully; native-camera capture is not
used by this project. Those warnings remain a packaging concern to revisit when
qualifying a deployment environment.

## Before evaluating accuracy

Label real event intervals and negative activity across different participants,
camera positions, lighting, phones and recording modes. Split by session and
participant. Report precision, recall, false alerts per video hour, assessable
coverage and processing time separately for each capability. Explicitly include
reflections, hands resting near devices, stationary phones, ordinary scrolling,
notifications, and application switches with similar visual layouts.
