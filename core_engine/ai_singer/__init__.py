"""AI singing synthesis and voice conversion boundaries."""

from core_engine.ai_singer.diff_singer_api import (
    DiffSingerClient,
    ExternalDiffSingerClient,
    PreviewSingingClient,
    SingingSegmentRequest,
)
from core_engine.ai_singer.rvc_infer import (
    BypassRvcInferencer,
    ExternalRvcInferencer,
    RvcInferencer,
    VoiceConversionRequest,
)
from core_engine.ai_singer.workflow import (
    LyricRewriteSingingRequest,
    LyricRewriteSingingResult,
    LyricRewriteSingingWorkflow,
)
from core_engine.ai_singer.backend_config import (
    LyricRewriteBackendConfig,
    load_lyric_rewrite_backend_config,
    parse_lyric_rewrite_backend_config,
)

__all__ = [
    "BypassRvcInferencer",
    "DiffSingerClient",
    "ExternalDiffSingerClient",
    "ExternalRvcInferencer",
    "LyricRewriteSingingRequest",
    "LyricRewriteSingingResult",
    "LyricRewriteSingingWorkflow",
    "LyricRewriteBackendConfig",
    "PreviewSingingClient",
    "RvcInferencer",
    "SingingSegmentRequest",
    "VoiceConversionRequest",
    "load_lyric_rewrite_backend_config",
    "parse_lyric_rewrite_backend_config",
]
