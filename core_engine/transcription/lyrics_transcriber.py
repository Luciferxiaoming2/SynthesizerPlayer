"""Adapters for generating editable lyrics when no LRC/SRT file exists."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import unicodedata
from collections.abc import Sequence

from core_engine.player.sync_buffer import read_audio


@dataclass(frozen=True)
class LyricsTranscriptionRequest:
    audio_path: Path
    output_path: Path


class LyricsTranscriber:
    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        raise NotImplementedError("Wire this adapter to a local ASR backend")


class PreviewLyricsTranscriber(LyricsTranscriber):
    """Writes a deterministic placeholder LRC so the import workflow is complete."""

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        audio, sample_rate = read_audio(request.audio_path)
        duration_seconds = audio.shape[0] / sample_rate
        midpoint_ms = max(0, round(duration_seconds * 500.0))

        # 这不是 ASR 结果，只是让没有歌词的歌曲也能进入“可编辑时间轴”。
        # 这不是识别结果；完整包里的“智能识别歌词”会替换为真实 ASR 结果。
        request.output_path.write_text(
            "\n".join(
                [
                    "[00:00.000]未找到歌词文件",
                    f"[{format_lrc_timestamp(midpoint_ms)}]请导入 .lrc/.srt，或使用智能识别歌词",
                ]
            ),
            encoding="utf-8",
        )
        return request.output_path


class ExternalCommandLyricsTranscriber(LyricsTranscriber):
    """Command adapter for optional local ASR tools."""

    def __init__(self, command_template: Sequence[str]) -> None:
        if not command_template:
            raise ValueError("command_template must not be empty")
        self._command_template = tuple(command_template)

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(self._render_command(request), check=True)
        if not request.output_path.exists():
            raise FileNotFoundError(f"external transcriber did not create {request.output_path}")
        return request.output_path

    def _render_command(self, request: LyricsTranscriptionRequest) -> list[str]:
        values = {
            "audio": str(request.audio_path),
            "output": str(request.output_path),
            "output_dir": str(request.output_path.parent),
        }
        return [part.format(**values) for part in self._command_template]


@dataclass(frozen=True)
class FasterWhisperConfig:
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = None
    beam_size: int = 8
    best_of: int = 5
    initial_prompt: str = "歌词只输出歌曲中实际唱出的内容。中文请使用简体中文，英文保持英文。"


class FasterWhisperLyricsTranscriber(LyricsTranscriber):
    """Local ASR adapter used by the packaged smart lyrics feature."""

    def __init__(self, config: FasterWhisperConfig | None = None) -> None:
        self._config = config or FasterWhisperConfig()

    def transcribe(self, request: LyricsTranscriptionRequest) -> Path:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "智能歌词识别组件未打包，无法生成歌词。"
            ) from exc

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            self._config.model_size,
            device=self._config.device,
            compute_type=self._config.compute_type,
        )
        segments, _info = model.transcribe(
            str(request.audio_path),
            language=self._config.language,
            beam_size=self._config.beam_size,
            best_of=self._config.best_of,
            initial_prompt=self._config.initial_prompt,
            condition_on_previous_text=False,
            no_speech_threshold=0.55,
            compression_ratio_threshold=2.4,
        )

        lines = []
        for segment in segments:
            text = normalize_generated_lyric_text(segment.text)
            if not text:
                continue
            start_ms = round(float(segment.start) * 1000.0)
            lines.append(f"[{format_lrc_timestamp(start_ms)}]{text}")

        if not lines:
            lines = ["[00:00.000]纯音乐或未识别到歌词"]
        request.output_path.write_text("\n".join(lines), encoding="utf-8")
        return request.output_path


def format_lrc_timestamp(position_ms: int) -> str:
    minutes, remainder = divmod(max(0, position_ms), 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


TRADITIONAL_PHRASES_TO_SIMPLIFIED = {
    "輪廓": "轮廓",
    "看著": "看着",
    "模樣": "模样",
    "臉色": "脸色",
    "說不出": "说不出",
}


TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {
        "臺": "台",
        "颱": "台",
        "灣": "湾",
        "萬": "万",
        "與": "与",
        "愛": "爱",
        "聽": "听",
        "說": "说",
        "話": "话",
        "夢": "梦",
        "還": "还",
        "這": "这",
        "那": "那",
        "裡": "里",
        "裏": "里",
        "為": "为",
        "會": "会",
        "來": "来",
        "時": "时",
        "間": "间",
        "風": "风",
        "雲": "云",
        "過": "过",
        "麼": "么",
        "嗎": "吗",
        "妳": "你",
        "誰": "谁",
        "開": "开",
        "關": "关",
        "讓": "让",
        "後": "后",
        "聲": "声",
        "無": "无",
        "沒": "没",
        "離": "离",
        "難": "难",
        "歡": "欢",
        "見": "见",
        "長": "长",
        "輕": "轻",
        "重": "重",
        "淚": "泪",
        "從": "从",
        "對": "对",
        "錯": "错",
        "點": "点",
        "舊": "旧",
        "終": "终",
        "隻": "只",
        "個": "个",
        "們": "们",
        "輪": "轮",
        "著": "着",
        "樣": "样",
        "臉": "脸",
        "顏": "颜",
        "願": "愿",
        "燈": "灯",
        "體": "体",
        "斷": "断",
        "線": "线",
        "處": "处",
        "頭": "头",
        "變": "变",
        "經": "经",
        "給": "给",
        "應": "应",
        "認": "认",
        "歲": "岁",
        "氣": "气",
        "搖": "摇",
        "遙": "遥",
        "遠": "远",
        "滿": "满",
        "單": "单",
        "雙": "双",
        "實": "实",
        "幾": "几",
        "帶": "带",
        "彎": "弯",
        "壞": "坏",
        "髮": "发",
        "發": "发",
        "葉": "叶",
        "邊": "边",
        "總": "总",
        "覺": "觉",
        "裏": "里",
        "叢": "丛",
        "區": "区",
        "畫": "画",
        "滿": "满",
        "壓": "压",
        "靜": "静",
        "響": "响",
        "轉": "转",
        "盡": "尽",
        "尋": "寻",
        "寫": "写",
        "寧": "宁",
        "樂": "乐",
        "檢": "检",
        "擇": "择",
        "導": "导",
        "齊": "齐",
        "顯": "显",
    }
)

TRADITIONAL_TO_SIMPLIFIED.update(
    str.maketrans(
        {
            "縮": "缩",
            "堅": "坚",
            "憶": "忆",
            "選": "选",
            "卻": "却",
            "證": "证",
            "臉": "脸",
            "龐": "庞",
            "過": "过",
            "這": "这",
            "來": "来",
            "個": "个",
            "們": "们",
            "後": "后",
            "讓": "让",
            "無": "无",
            "從": "从",
            "對": "对",
            "應": "应",
            "發": "发",
            "現": "现",
            "裡": "里",
            "裏": "里",
            "著": "着",
            "點": "点",
            "體": "体",
            "樂": "乐",
            "聲": "声",
            "傷": "伤",
            "離": "离",
            "難": "难",
            "關": "关",
            "開": "开",
            "長": "长",
            "聽": "听",
            "說": "说",
            "話": "话",
            "愛": "爱",
            "夢": "梦",
            "為": "为",
            "會": "会",
            "還": "还",
            "時": "时",
            "間": "间",
            "風": "风",
            "雲": "云",
            "誰": "谁",
            "嗎": "吗",
            "麼": "么",
        }
    )
)


def normalize_generated_lyric_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for source, target in TRADITIONAL_PHRASES_TO_SIMPLIFIED.items():
        normalized = normalized.replace(source, target)
    normalized = convert_generated_chinese_to_simplified(normalized)
    cleaned = "".join(
        char for char in normalized.strip()
        if char == "\t" or not unicodedata.category(char).startswith("C")
    )
    if is_instruction_hallucination(cleaned):
        return ""
    return cleaned


def convert_generated_chinese_to_simplified(text: str) -> str:
    try:
        from opencc import OpenCC
    except ImportError:
        return text.translate(TRADITIONAL_TO_SIMPLIFIED)
    return OpenCC("t2s").convert(text).translate(TRADITIONAL_TO_SIMPLIFIED)


def is_instruction_hallucination(text: str) -> bool:
    compact = text.replace(" ", "").replace(",", "，").replace(".", "。")
    phrases = (
        "歌词只输出歌曲中实际唱出的内容",
        "只输出歌曲中实际唱出的内容",
        "中文请使用简体中文",
        "英文保持英文",
        "请使用简体中文或英文",
        "不要使用繁体中文",
        "使用简体中文",
        "使用繁体中文",
        "输出歌词",
    )
    return any(phrase in compact for phrase in phrases)
