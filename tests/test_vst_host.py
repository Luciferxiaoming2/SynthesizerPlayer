from pathlib import Path

import numpy as np

from core_engine.dsp.vst_host import OfflineEffectConfig, VstEffectChain, apply_gain


def test_apply_gain_uses_decibels():
    audio = np.ones((4, 1), dtype=np.float32)

    processed = apply_gain(audio, 6.0)

    assert processed.shape == audio.shape
    assert float(processed[0, 0]) > 1.9


def test_vst_effect_chain_processes_gain_without_pedalboard():
    audio = np.full((4, 1), 0.5, dtype=np.float32)
    chain = VstEffectChain(OfflineEffectConfig(gain_db=-6.0))

    processed = chain.process(audio, sample_rate=48_000)

    assert processed.shape == audio.shape
    assert float(processed[0, 0]) < 0.5


def test_add_plugin_rejects_missing_path():
    chain = VstEffectChain()

    try:
        chain.add_plugin(Path("missing.vst3"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing plugin should fail")

