from harness.cli_harness.generate_mock_audio import build_mock_stems


def test_build_mock_stems_returns_aligned_mono_tracks():
    vocal, instrumental = build_mock_stems(sample_rate=1000, duration_seconds=0.5)

    assert vocal.shape == instrumental.shape
    assert vocal.shape == (500, 1)

