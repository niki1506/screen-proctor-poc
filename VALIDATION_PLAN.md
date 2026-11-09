# Validation before general use

Status: pending. No held-out real-video accuracy claim is made. The repeatedly
reviewed reference video is a regression case. Synthetic clips test implementation
behavior, not real-world accuracy. No new phone-detector tuning is part of 0.4.3.

## Dataset and annotations

1. Collect separately consented recordings covering external camera, webcam,
   direct screen and combined modes. Vary resolution, lighting, camera motion,
   display angle, operating system, application layouts and available frame rate.
2. Include positives and long negative periods. Include nuisance examples:
   notifications, scrolling, window resizing, physical screen obstruction,
   reflections and displayed people. Include short events, localization loss,
   scene cuts, corrupt input and no usable screen.
3. Annotate recording-relative event start/end intervals, event category, and
   observable/unassessed intervals. Use distinct labels for visual content change,
   physical screen occlusion, and verified application transition. Verify app
   changes with synchronized direct recording or independently checked telemetry.
4. Review ambiguous labels with a second annotator. Preserve uncertainty; never
   treat an unreadable application as proof of no AI usage. Phone placement and
   its derived possible-use label count as one incident when they share evidence.
5. Split by participant/session and recording setup into development, validation
   and held-out test sets. Keep this reference clip in regression/development.
   Freeze thresholds before running held-out tests. Do not tune on test results.

## Matching and metrics

Predeclare one-to-one event matching rules. For interval events, use same-category
intersection-over-union >= 0.5; for transitions, use onset within 1 second of the
annotated transition. Report sensitivity to tolerance rather than hiding boundary
uncertainty. A prediction can match at most one annotation and vice versa.
For visual changes, use the estimated change window; report confirmation latency
separately. Exclude unobservable periods from detection denominators, but always
report their duration and coverage separately so exclusions cannot hide failures.

Report by capability and recording mode:

| Metric | Definition |
|---|---|
| Event precision | Matched predictions / all assessable predictions |
| Event recall | Matched annotations / all assessable annotations |
| False alerts per hour | Unmatched predictions / assessable recording hours |
| Coverage | Usable samples / all sampled frames; also annotate duration coverage |
| AI readability | Readable scheduled scans / scheduled scans (separate from screen coverage) |
| Timing error | Estimated transition boundary error relative to annotations |
| Confirmation latency | Confirmation time minus annotated transition time |
| Processing cost | Wall-clock seconds / video duration on named hardware |

Record sample counts, annotated hours, dataset split, software/model checksums,
configuration, and uncertainty intervals. Evaluate visual changes and verified
app changes separately. Do not interpret heuristic evidence scores as calibrated
probabilities. Define acceptance thresholds with the product owner before testing.

## Review and release

Inspect false positives and negatives by failure mode. Preserve representative
regression cases and rerun them after relevant changes. Publish measured results
and remaining unassessed cases. A passing unit suite or one working recording
is insufficient to claim that any arbitrary input video can be assessed reliably.
