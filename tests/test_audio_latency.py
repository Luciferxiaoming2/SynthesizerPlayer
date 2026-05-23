import numpy as np

from harness.eval_harness.audio_latency_test import evaluate_latency, estimate_latency_samples


def test_estimate_latency_samples_detects_candidate_delay():
    reference = np.zeros(1000, dtype=np.float32)
    candidate = np.zeros(1000, dtype=np.float32)
    reference[100:140] = 1.0
    candidate[112:152] = 1.0

    latency, score = estimate_latency_samples(reference, candidate, max_lag_samples=50)

    assert latency == 12
    assert score > 0.99


def test_evaluate_latency_fails_when_outside_tolerance():
    reference = np.zeros(1000, dtype=np.float32)
    candidate = np.zeros(1000, dtype=np.float32)
    reference[100:140] = 1.0
    candidate[130:170] = 1.0

    result = evaluate_latency(
        reference=reference,
        candidate=candidate,
        sample_rate=1000,
        max_lag_ms=100,
        tolerance_ms=5,
    )

    assert result.latency_samples == 30
    assert not result.passed

