"""Play aligned stems through the optional SoundDevice output adapter."""

import argparse
from pathlib import Path

from core_engine.player.playback_engine import DualTrackPlaybackEngine
from core_engine.player.sounddevice_output import SoundDeviceOutput, SoundDeviceOutputConfig
from core_engine.player.sync_buffer import load_stem_pair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play aligned vocal and instrumental stems.")
    parser.add_argument("--vocal", required=True, type=Path)
    parser.add_argument("--instrumental", required=True, type=Path)
    parser.add_argument("--block-size", type=int, default=1024)
    parser.add_argument("--device", default=None)
    return parser


def parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    raise ValueError("expected on/off")


def format_status(engine: DualTrackPlaybackEngine) -> str:
    snapshot = engine.snapshot()
    controls = snapshot.controls
    return (
        f"position={snapshot.position_seconds:.3f}/{snapshot.duration_seconds:.3f}s "
        f"playing={snapshot.is_playing} "
        f"vocal_gain={controls.vocal_gain:.3f} "
        f"instrumental_gain={controls.instrumental_gain:.3f} "
        f"vocal_muted={controls.vocal_muted} "
        f"instrumental_muted={controls.instrumental_muted} "
        f"vocal_solo={controls.vocal_solo} "
        f"instrumental_solo={controls.instrumental_solo}"
    )


def apply_playback_command(engine: DualTrackPlaybackEngine, command: str) -> tuple[bool, str]:
    parts = command.strip().split()
    if not parts:
        return True, ""

    verb = parts[0].lower()
    if verb in {"q", "quit", "exit"}:
        return False, "stopping"
    if verb in {"status", "st"}:
        return True, format_status(engine)
    if verb == "play":
        engine.play()
        return True, "playing"
    if verb == "pause":
        engine.pause()
        return True, "paused"
    if verb == "stop":
        engine.stop()
        return True, "stopped"
    if verb == "seek" and len(parts) == 2:
        engine.seek_seconds(float(parts[1]))
        return True, format_status(engine)
    if verb == "gain" and len(parts) == 3:
        target = parts[1].lower()
        value = float(parts[2])
        if target == "vocal":
            engine.set_gains(vocal_gain=value)
        elif target == "instrumental":
            engine.set_gains(instrumental_gain=value)
        else:
            raise ValueError("gain target must be vocal or instrumental")
        return True, format_status(engine)
    if verb == "mute" and len(parts) == 3:
        target = parts[1].lower()
        value = parse_bool(parts[2])
        if target == "vocal":
            engine.set_mute(vocal_muted=value)
        elif target == "instrumental":
            engine.set_mute(instrumental_muted=value)
        else:
            raise ValueError("mute target must be vocal or instrumental")
        return True, format_status(engine)
    if verb == "solo" and len(parts) == 3:
        target = parts[1].lower()
        value = parse_bool(parts[2])
        if target == "vocal":
            engine.set_solo(vocal_solo=value)
        elif target == "instrumental":
            engine.set_solo(instrumental_solo=value)
        else:
            raise ValueError("solo target must be vocal or instrumental")
        return True, format_status(engine)

    raise ValueError(
        "commands: status, play, pause, stop, seek <seconds>, "
        "gain <vocal|instrumental> <value>, mute <vocal|instrumental> <on|off>, "
        "solo <vocal|instrumental> <on|off>, quit"
    )


def run_command_loop(engine: DualTrackPlaybackEngine) -> None:
    print("commands: status, play, pause, stop, seek, gain, mute, solo, quit")
    keep_running = True
    while keep_running:
        try:
            keep_running, message = apply_playback_command(engine, input("> "))
        except (ValueError, TypeError) as exc:
            message = f"error: {exc}"
        if message:
            print(message)


def main() -> None:
    args = build_parser().parse_args()
    buffers = load_stem_pair(args.vocal, args.instrumental)
    engine = DualTrackPlaybackEngine(buffers)
    output = SoundDeviceOutput(
        engine,
        SoundDeviceOutputConfig(block_size=args.block_size, device=args.device),
    )
    output.start()
    try:
        run_command_loop(engine)
    finally:
        output.stop()


if __name__ == "__main__":
    main()
