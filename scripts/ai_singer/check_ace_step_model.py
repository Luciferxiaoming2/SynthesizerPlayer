from __future__ import annotations

import importlib.util
from pathlib import Path

from core_engine.ai_singer.backend_config import is_ace_step_model_dir


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    model_dir = root / "plugins" / "models" / "ace-step" / "acestep-v15-sft"
    print(f"ACE-Step 模型目录: {model_dir}")
    print(f"模型文件完整: {'是' if is_ace_step_model_dir(model_dir) else '否'}")
    print(f"acestep 运行库: {'已安装' if importlib.util.find_spec('acestep') else '未安装'}")
    print(f"diffusers 运行库: {'已安装' if importlib.util.find_spec('diffusers') else '未安装'}")
    if not is_ace_step_model_dir(model_dir):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
