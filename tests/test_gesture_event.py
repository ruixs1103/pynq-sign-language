import pytest

from gesture_event import GestureEventGate


def result(label, confidence):
    return {"label": label, "confidence": confidence, "text": label}


def test_requires_stable_predictions_and_emits_once():
    gate = GestureEventGate(min_confidence=.3, stable_windows=3, release_windows=2)
    assert gate.update(result("hello", .8)) is None
    assert gate.update(result("thanks", .9)) is None
    assert gate.update(result("hello", .7)) is None
    assert gate.update(result("hello", .8)) is None
    event = gate.update(result("hello", .9))
    assert event["id"] == 1
    assert event["result"]["label"] == "hello"
    assert event["result"]["confidence"] == .8
    assert gate.update(result("hello", .9)) is None


def test_neutral_gap_rearms_and_ids_are_monotonic():
    gate = GestureEventGate(stable_windows=2, release_windows=2)
    assert gate.update(result("help", .8)) is None
    assert gate.update(result("help", .8))["id"] == 1
    assert gate.update(result("unknown", 1.0)) is None
    assert gate.update(result("unknown", 1.0)) is None
    assert gate.state == "ready"
    assert gate.update(result("thanks", .7)) is None
    assert gate.update(result("thanks", .9))["id"] == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_confidence": -1},
        {"min_confidence": 1.1},
        {"stable_windows": 0},
        {"release_windows": 0},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        GestureEventGate(**kwargs)
