import pytest

from screenproctor.events import Events


def observation(kind="phone_present", score=0.8):
    return {kind: (score, {"reason": "test"})}


def test_short_detection_is_not_reported():
    events = Events(minimum=0.75)
    events.update(0, observation())
    events.update(0.25, {})
    assert events.close() == []


def test_actual_support_and_boundaries():
    events = Events(minimum=0.75)
    for t in (0, 0.25, 0.5, 0.75):
        events.update(t, observation())
    events.update(1, {})
    result = events.close()[0]
    assert result["start_seconds"] == 0
    assert result["end_seconds"] == 0.75
    assert result["observed_support_seconds"] == 0.75


def test_one_missing_sample_does_not_fragment_event():
    events = Events(minimum=0.5, gap=0.6)
    for t in (0, 0.25, 0.5, 0.75, 1, 1.25, 1.5):
        events.update(t, {} if t == 0.75 else observation())
    result = events.close()
    assert len(result) == 1
    assert result[0]["observed_support_seconds"] == 1.0


def test_missing_time_does_not_qualify_as_observed_support():
    events = Events(minimum=0.75, gap=1)
    events.update(0, observation())
    events.update(0.25, {})
    events.update(0.75, observation())
    assert events.close() == []


def test_scene_boundary_prevents_merging():
    events = Events(minimum=0.25)
    events.update(0, observation())
    events.update(0.25, observation())
    events.boundary()
    events.update(0.5, observation())
    events.update(0.75, observation())
    assert len(events.close()) == 2


def test_parallel_events_remain_separate():
    events = Events(minimum=0.25)
    obs = {**observation(), **observation("additional_person_candidate")}
    events.update(0, obs)
    events.update(0.25, obs)
    assert {e["type"] for e in events.close()} == set(obs)


def test_nonmonotonic_time_rejected():
    events = Events()
    events.update(1, {})
    with pytest.raises(ValueError):
        events.update(0.5, {})
