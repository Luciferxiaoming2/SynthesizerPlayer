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

__all__ = [
    "BypassRvcInferencer",
    "DiffSingerClient",
    "ExternalDiffSingerClient",
    "ExternalRvcInferencer",
    "LyricRewriteSingingRequest",
    "LyricRewriteSingingResult",
    "LyricRewriteSingingWorkflow",
    "PreviewSingingClient",
    "RvcInferencer",
    "SingingSegmentRequest",
    "VoiceConversionRequest",
]
