import json

from core_engine.ai_singer.backend_config import (
    LyricRewriteBackendConfig,
    load_lyric_rewrite_backend_config,
    parse_lyric_rewrite_backend_config,
)


def test_lyric_rewrite_backend_defaults_to_preview(tmp_path):
    config = load_lyric_rewrite_backend_config(tmp_path)

    assert config == LyricRewriteBackendConfig()
    assert config.label == "内置实验预览"


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

    assert config.backend == "external"
    assert config.diff_command[0] == "python"
    assert config.rvc_model_path == tmp_path / "models" / "voice.pth"
    assert config.rvc_command[-1] == "{model}"
    assert config.config_path == config_path
