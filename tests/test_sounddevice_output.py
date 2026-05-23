from core_engine.player.sounddevice_output import list_output_devices


def test_list_output_devices_filters_input_only_devices():
    devices = list_output_devices(
        lambda: [
            {"name": "Mic", "max_output_channels": 0, "default_samplerate": 48_000},
            {"name": "Speakers", "max_output_channels": 2, "default_samplerate": 44_100},
        ]
    )

    assert len(devices) == 1
    assert devices[0].id == 1
    assert devices[0].label == "1: Speakers"
    assert devices[0].default_sample_rate == 44_100.0
