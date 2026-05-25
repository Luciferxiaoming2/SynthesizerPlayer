import json

from core_engine.ai_singer.backend_config import (
    LyricRewriteBackendConfig,
    load_lyric_rewrite_backend_config,
    parse_lyric_rewrite_backend_config,
)


def test_lyric_rewrite_backend_defaults_to_preview(tmp_path):
    config = load_lyric_rewrite_backend_config(tmp_path)

    assert config == LyricRewriteBackendConfig(backend="local_tts")
    assert config.label == "本机轻量改词唱"
    assert config.can_replace_audio is True


def test_lyric_rewrite_backend_config_loads_external_command(tmp_path):
    config_path = tmp_path / "ai_singer_backend.json"
    config_path.write_text(
        json.dumps(
            {
                "backend": "external",
                "diff_command": ["python", "infer.py", "--lyric", "{lyric}", "--output", "{output}"],
                "rvc_model_path": "models/voice.pth",
                "rvc_command": ["python", "rvc.py", "--source", "{source}", "--model", "{model}"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = parse_lyric_rewrite_backend_config(config_path)

    assert config.backend == "external_svs"
    assert config.diff_command[0] == "python"
    assert config.rvc_model_path == tmp_path / "models" / "voice.pth"
    assert config.rvc_command[-1] == "{model}"
    assert config.config_path == config_path


def test_lyric_rewrite_backend_config_loads_vevo_alias(tmp_path):
    config_path = tmp_path / "ai_singer_backend.json"
    config_path.write_text(
        json.dumps(
            {
                "backend": "vevo1.5",
                "edit_command": [
                    "python",
                    "edit.py",
                    "--source",
                    "{source}",
                    "--text",
                    "{lyric}",
                    "--output",
                    "{output}",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = parse_lyric_rewrite_backend_config(config_path)

    assert config.backend == "content_edit"
    assert config.label == "Vevo/内容编辑后端"
    assert config.uses_content_editor is True
    assert config.edit_command[-1] == "{output}"


def test_lyric_rewrite_backend_auto_detects_ace_step_model(tmp_path):
    model_dir = tmp_path / "plugins" / "models" / "ace-step" / "acestep-v15-sft"
    model_dir.mkdir(parents=True)
    for name in [
        "model.safetensors",
        "config.json",
        "configuration_acestep_v15.py",
        "modeling_acestep_v15_base.py",
        "silence_latent.pt",
    ]:
        (model_dir / name).write_text("fake", encoding="utf-8")

    config = load_lyric_rewrite_backend_config(tmp_path)

    assert config.backend == "local_tts"
    assert config.ace_model_path is None
    assert config.label == "本机轻量改词唱"
    assert config.can_replace_audio is True


def test_lyric_rewrite_backend_detects_ace_step_from_portable_release_layout(tmp_path):
    app_root = tmp_path / "release" / "AudioForgePortable_next"
    app_root.mkdir(parents=True)
    model_dir = tmp_path / "plugins" / "models" / "ace-step" / "acestep-v15-sft"
    model_dir.mkdir(parents=True)
    for name in [
        "model.safetensors",
        "config.json",
        "configuration_acestep_v15.py",
        "modeling_acestep_v15_base.py",
        "silence_latent.pt",
    ]:
        (model_dir / name).write_text("fake", encoding="utf-8")

    config = load_lyric_rewrite_backend_config(app_root)

    assert config.backend == "local_tts"
    assert config.ace_model_path is None


def test_lyric_rewrite_backend_config_accepts_ace_step_alias(tmp_path):
    model_dir = tmp_path / "models" / "ace"
    model_dir.mkdir(parents=True)
    config_path = tmp_path / "ai_singer_backend.json"
    config_path.write_text(
        json.dumps(
            {
                "backend": "acestep-v15",
                "ace_model_path": str(model_dir),
                "edit_command": ["python", "ace_edit.py", "--model-dir", "{model_dir}", "--output", "{output}"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = parse_lyric_rewrite_backend_config(config_path)

    assert config.backend == "ace_step"
    assert config.ace_model_path == model_dir
    assert config.can_replace_audio is True
