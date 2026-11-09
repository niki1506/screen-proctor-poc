# Engine and report 0.4.4: missed pale-page transitions

The preceding reference review missed two real content changes before 18 seconds.
The 18–19 second alert is a separate return to the sparse page with a phone placed
against the display; it was not a delayed timestamp for the earlier change.

Root cause: the pixel comparator required >30 levels of color difference over
8% of the display. Small muted text can change across a pale page while staying
below that threshold. Candidates also lost support when the changed view was
first encountered during a frame with high motion. Successive differences did
not check accumulated drift against a fixed candidate view.

Fix: retain the existing color comparison and add spatially tolerant unmatched
text/layout-edge comparison. Require a substantial proportion of edges to change.
Use a fixed candidate reference to require sustained stability, starting a new
candidate on a moving frame without counting multiple changing views as stable.
Phone detector/placement thresholds are unchanged. Evidence now refreshes from
the latest unchanged view and includes exact source-frame capture timestamps.
The changed_fraction metric is the maximum color/edge fraction, identified by
comparison_metric=max_color_or_unmatched_edge_fraction.

Fresh full reference-video inference at 4 FPS (125 samples) produced:

| Estimated screen-change window | Confirmation |
|---|---|
| 11.760–12.000 s | 12.752 s |
| 13.002–13.252 s | 14.002 s |
| 18.757–19.503 s | 20.255 s |
| 22.007–22.257 s | 23.007 s |
| 25.260–25.503 s | 26.253 s |

No screen alerts precede the first actual transition. Screen coverage remains
84%, with 0–5.003 s unassessed. Non-screen events match the preceding report.
The estimates reflect 4 FPS sampling; they are not exact physical onset times.
See validation/reviewed-reference-v044/report.pdf. This is regression evidence,
not held-out accuracy validation.

87 automated checks cover low-contrast changes, translation/exposure stability,
progressive layout drift, source-frame evidence provenance, and live PDF reload
in addition to the preceding suite. Old reports remain preserved; rerun analysis
to get the additional events. The live UI warns when displaying older results.

# Report format 0.4.3

- PDF reports embed screenshots and before/after screen evidence; existing reports
  can be exported with local evidence without repeating inference.
- Exact matching placement and derived possible-use labels form one readable incident.
  Original events, phone thresholds, support intervals and engine 0.4.2 are unchanged.
- Screen changes are visual observations, not verified application switches.
- Coverage and unavailable intervals are prominent. Coverage is not accuracy.
- Report metadata and VALIDATION_PLAN.md explicitly retain pending held-out validation.
- Reference report (6) has three screen changes and six grouped observations from
  seven raw records. Late transition remains 25.260–25.753 s, confirmed at 26.505 s.

# Version 0.4.2 — record the estimated window as the screen-change time

The running UI refreshes its stateless review helpers on rerun. This fixes stale
module imports after an update without restarting the server or losing sessions.
A regression test recreates the previously cached module missing the new helpers.

Screen changes are labelled **Screen change**, using the estimated transition
window in the JSON summary, UI and HTML review. Confirmation time is separate.
No application or AI identity is required for this alert.

For the late transition in `report (5).json`:

- Recorded screen-change window: **25.260–25.753 seconds**.
- Confirmed at: **26.505 seconds**.
- The original stable-observation interval remains in the detailed event fields
  for compatibility. It is not presented as the change onset.

The detector's thresholds and evidence are unchanged. Existing 0.4 reports use
these timing labels immediately after a UI refresh. Downloaded JSON refreshes
the derived summary too, without altering the stored source observations. Future runs also record an
explicit event label and `confirmed_at_seconds`. An updated review of the uploaded
report, with provenance and original measurements retained, is available at
[report.json](validation/reviewed-reference-v042/report.json) and
[review.html](validation/reviewed-reference-v042/review.html).

76 tests cover estimated-window presentation, separate confirmation times,
backward compatibility, UI rendering and the existing detection pipeline.

The earlier notes below are retained as history.

---

# Version 0.4.1 — make detected screen changes clear

This update changes review presentation and report summaries. The 0.4 detection
results are retained: the latest user-uploaded report already contains the late
screen change at 25.753–26.505 seconds. A readable AI brand is not required to
flag that change; application identification remains a separate, uncertain result.

- The UI shows a prominent screen-change count, uses plain event labels and opens
  the latest before/after comparison first, above the assessments.
- AI is labelled application identification, with its explanation in details.
  An unreadable application name does not suppress or override a screen alert.
- Existing 0.4 reports use this presentation without another inference run.
- New JSON reports start with `screen_change_summary`. New runs also include
  `review.html`, a local page showing screen comparisons with the latest first.
- A review of `report (3).json`, retaining its original events and analysis version,
  is available at [review.html](validation/reviewed-reference-v041-summary/review.html).
  Its provenance identifies it as a derived review, not a new inference result.

73 tests pass, including an actual Streamlit render of an existing 0.4 report
with a detected screen change and unknown AI identity. Summary tests exclude
comparison resets, preserve unavailable results, and verify safe HTML rendering.
Existing detector, timing and evidence tests remain unchanged in purpose.

The earlier engine notes below are retained as history.

---

# Engine 0.4 — full display tracking and comparison across short gaps

## Corrections

- The former locator could follow a bright application pane instead of the outer
  display, losing the dark side panel. Long line-segment intersections and edge
  support now propose the physical display boundary. Text evidence is retained
  for acquisition to reject blank laptop backs. Optical flow tracks the border;
  a larger enclosing border can replace an internal-pane track.
- Polygon-overlap checks use pixel-like coordinate units to avoid false zero
  overlaps for nearly identical normalized quadrilaterals. This prevents
  unnecessary tracking loss and comparison resets from subpixel jitter.
- After tracking loss, a much smaller text-bearing pane cannot silently replace
  the previous full display. Unsupported regions remain unavailable.
- Short gaps retain a compatible baseline for up to five seconds, while breaking
  all positive dwell support. Recovered changes carry `comparison_gap`, uncertain
  timing, and a change window. Long gaps or incompatible regions emit
  `screen_comparison_reset`; they do not masquerade as content changes.
- Reports and the UI list unavailable screen intervals. Each visual change has
  an application-identity field and nearby `ai_interface_check` context. A clear
  visual change does not require readable AI-brand text. Nearby AI visibility
  does not prove the destination or active assistance.
- Phone and AI identity detection rules and model files are unchanged. No new
  dependencies or cloud calls are introduced. Refresh and analyze again; saved
  reports are preserved.

## Validation

69 tests pass, including split dark/bright displays, rejected pane reacquisition,
short-gap changes with before/after evidence, unchanged gap recovery, long-gap
resets, incompatible-crop resets, and AI context linked to visual changes.
Lint and formatting pass. The generated direct-screen demo still produces its
expected two transitions near 5 and 10 seconds.

See [the engine 0.4 reference report](validation/reviewed-reference-v04/report.json)
for final reference results and full-display before/after evidence. The previously
missed late side-panel layout is now detected as a visual change. Its application
remains unidentified because the source text is too small/blurred for reliable OCR.
These are regression checks on a reviewed clip, not independent accuracy metrics
for arbitrary videos. Geometric border proposals, motion tracking and semantic
recognition remain heuristic; occlusion, extreme perspective and unseen layouts
can still cause missed or false alerts.

The earlier engine notes below are retained as history.

---

# Engine 0.3 — placement risk and periodic AI-interface recognition

The updated engine adds the two missing analysis paths. Refresh the UI and run
Analyze video again; previous reports and their evidence remain unchanged.

## Behavior

- Phone placement can produce `possible_phone_use` without visible wrists or
  hand contact. Confirmed portrait phones overlapping the laptop produce
  `phone_positioned_for_viewing`. When the generic detector misses the object,
  conservative dark-portrait geometry produces `phone_placement_candidate`,
  with explicit uncertainty about object identity. Neither establishes active use.
- Hand interaction remains a separate assessment. Placement does not invent a
  touch/handling event or relax the corroborated phone detector's thresholds.
- Local OCR checks run periodically (default 1 second), independently of screen
  transitions and automatic display localization. External mode scans the whole
  detected laptop box, including side panels outside the white text quad.
- AI alerts require a readable known-service header/domain and chat controls, or
  a generic AI-assistant header plus controls for an unidentified candidate.
  Brand mentions in documents alone do not qualify. No cloud service is called.
- AI assessments record readable/scheduled scan counts, preview the inspected
  area, and preserve `not_assessable` for unreadable text or OCR failure.
- UI controls expose both checks and scan interval; old reports prompt reanalysis.

## Validation

60 tests pass, including real local OCR on a readable test image, static-screen
AI events, full-laptop inspection with display tracking disabled, mention/domain
negatives, missing OCR, no-wrist placement, accessory/panel negatives, and existing
video/event regressions. Lint, formatting and dependency consistency pass.

The original 31.09-second video at 4 FPS (125 samples) produces:

| Check | Result |
|---|---|
| Upright phone placement / possible use | 20.505–24.258 s, 2.752 s positive support; evidence box covers the actual upright phone |
| Desk-accessory false phone / interaction alerts | Absent |
| Phone interaction | No sustained event; placement does not require interaction |
| Additional person | 5.003–11.760 s, unchanged |
| Desk phone presence | 5.003–18.757 s, unchanged |
| Screen-view changes | Four candidates, unchanged; not four verified application switches |
| AI interface | Not assessable: 0/31 scheduled scans readable enough for recognition |

See [the engine 0.3 reference report](validation/reviewed-reference-v03/report.json).
The final dark panel is now included in periodic inspection, but its text is too
small/blurred to name an AI service reliably. This remains an input-quality limit,
not a successful AI identification. No AI-use claim is generated for that panel.
The phone geometry is tuned using this reference, so these results are regression
evidence, not independent accuracy measurements on unseen sessions.

A generated, readable static AI fixture produces `ai_interface_visible` at 0–5 s
from 6/6 readable OCR scans, with no screen-change event. See
[the static AI report](validation/static-ai-v03/report.json). This validates the
independent periodic path; it is not evidence of accuracy on arbitrary AI UIs.

The engine 0.2 results below are retained as history.

---

# Engine 0.2 — report corrections

The screenshots exposed errors in the baseline model and an incomplete default
screen-analysis path. The earlier reports are preserved as historical artifacts;
they are not corrected by installing this version. Run a new analysis.

## Changes

* YOLO11m now supplies full-frame people, laptop and phone detections. YOLO11n
  checks overlapping phone crops; the pose model remains YOLO11n-pose.
* A cropped prediction alone cannot establish phone presence. A phone needs
  matching full-frame/crop boxes, both at least 0.55 (or the user threshold if
  higher). Small images without crop passes need a full-frame score of 0.65.
  This reduces false positives at the cost of missing small/occluded phones.
* Interaction rules receive only the corroborated phones. The desk-accessory
  error no longer propagates into a phone-interaction event in this test clip.
* Low-contrast person-like silhouettes are marked ambiguous and are not included
  in the additional-person count. This does not establish whether they are
  reflections or real distant people; those cases still need review.
* External-camera mode attempts automatic display localization without manual
  corners. It detects text-bearing quadrilaterals inside laptops and tracks their
  borders with forward/backward optical flow and a RANSAC homography. It can
  reacquire after loss/cuts. Unsupported regions remain unassessed.
* Subpixel display coordinates are retained during tracking. Small screen-crop
  misalignment and bounded exposure shifts are compensated before comparison.
* Reports include display previews, source coordinates, before/after crops, and
  `candidate_detected` summaries instead of implying verified behavior.
* The UI identifies reports from the old engine and asks for a new analysis.

## Validation

42 automated tests passed, including new checks for crop-only false positives,
spatial agreement, ambiguous silhouettes, automatic display acquisition, camera
translation, exposure shifts, and external analysis without manual corners.
Lint and formatting checks passed. Dependencies are unchanged.

The full reference clip was processed at 4 FPS (125 samples) with the new models.
See [the updated report](validation/reviewed-reference/report.json).

| Output | Result |
|---|---|
| Additional person | 5.003–11.760 s; two foreground people visible |
| Phone presence | 5.003–18.757 s; actual phone beside laptop |
| Earlier desk-accessory phone alerts | Absent in this run |
| Earlier possible-phone-interaction alert | Absent in this run |
| Later silhouette additional-person alert | Absent in this run |
| Automatic screen coverage | 93/125 samples (74.4%), first usable display at 5.003 s |
| Screen-view changes | Four candidates around 12–13, 14–15, 19–20, and 22–23 s |

The four visual changes are **not four verified application switches**. Review
the before/after evidence: camera/view changes, page content, a physical phone
covering the display, and a notification/banner can all contribute. The late
side-by-side/window-layout change is not reliably identified as an app switch.
The upright phone visible later in the clip is still missed by the corroboration
rule. General recall and accuracy are not established by one reference video.

For reliable app-switch evidence, prefer a synchronized direct screen recording
and client telemetry. For an external-camera-only input, inspect the auto-selected
display; optional manual corners are still useful when localization is incomplete.
