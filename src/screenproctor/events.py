"""Time-based event grouping with gap tolerance and independent subtypes."""

from dataclasses import dataclass, field


@dataclass
class State:
    start: float
    last: float
    observed: float = 0.0
    peak: float = 0.0
    evidence: dict = field(default_factory=dict)
    samples: int = 1


class Events:
    def __init__(self, minimum=0.75, gap=0.6):
        self.minimum = minimum
        self.gap = gap
        self.active = {}
        self.finished = []
        self.previous_time = None
        self.previous_keys = set()

    def update(self, timestamp, observations):
        """observations maps event type to (score, evidence). Scores are heuristics."""
        if self.previous_time is not None and timestamp < self.previous_time:
            raise ValueError("Event timestamps must be monotonic")
        for kind in list(self.active):
            if timestamp - self.active[kind].last > self.gap:
                self._finish(kind)
        for kind, (score, evidence) in observations.items():
            state = self.active.get(kind)
            if state is None:
                self.active[kind] = State(
                    timestamp, timestamp, peak=score, evidence=evidence
                )
                continue
            if kind in self.previous_keys and self.previous_time is not None:
                state.observed += timestamp - self.previous_time
            state.last = timestamp
            state.samples += 1
            if score > state.peak:
                state.peak = score
                state.evidence = evidence
        self.previous_time = timestamp
        self.previous_keys = set(observations)

    def _finish(self, kind):
        state = self.active.pop(kind)
        if state.observed + 1e-6 < self.minimum or state.samples < 2:
            return
        self.finished.append(
            {
                "type": kind,
                "start_seconds": round(state.start, 3),
                "end_seconds": round(state.last, 3),
                "duration_seconds": round(state.last - state.start, 3),
                "observed_support_seconds": round(state.observed, 3),
                "evidence_score": round(state.peak, 3),
                "score_is_calibrated_probability": False,
                **state.evidence,
            }
        )

    def boundary(self):
        """Do not bridge shots, invalid images, or changed capture layouts."""
        for kind in list(self.active):
            self._finish(kind)
        self.previous_keys.clear()
        self.previous_time = None

    def close(self):
        self.boundary()
        return sorted(self.finished, key=lambda x: (x["start_seconds"], x["type"]))
