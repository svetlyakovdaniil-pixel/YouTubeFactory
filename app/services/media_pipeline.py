import json
import subprocess
from pathlib import Path

from app.services.channel_library import ChannelLibrary, PROJECT_ROOT


PROFILE_PATH = PROJECT_ROOT / "config" / "stream_profile.json"

DEFAULT_PROFILE = {
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "bitrate": "6000k",
        "maxrate": "6000k",
        "bufsize": "12000k",
        "preset": "veryfast",
        "crf": 21,
        "keyframe_seconds": 2,
    },
    "audio": {
        "bitrate": "192k",
        "sample_rate": 48000,
    },
}


def ensure_stream_profile():
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(
            json.dumps(DEFAULT_PROFILE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def run_cmd(cmd, timeout=None):
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    return result


def ffprobe(path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    result = run_cmd(cmd)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    return json.loads(result.stdout)


def get_video_stream(probe):
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream

    return None


def parse_fps(value):
    value = str(value or "")

    if "/" in value:
        left, right = value.split("/", 1)

        try:
            right_float = float(right)

            if right_float == 0:
                return 0

            return round(float(left) / right_float, 3)
        except Exception:
            return 0

    try:
        return float(value)
    except Exception:
        return 0


def output_name(source_path):
    source = Path(source_path)
    return f"{source.stem}_stream_ready.mp4"


def build_video_output_path(library, source_path):
    return library.loop_videos_ready_dir / output_name(source_path)


def is_ready_video(path, profile=None):
    profile = profile or ensure_stream_profile()
    probe = ffprobe(path)
    stream = get_video_stream(probe)

    if not stream:
        return False

    video = profile["video"]

    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    fps = parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    codec = str(stream.get("codec_name") or "").lower()

    return (
        codec == "h264"
        and width == int(video["width"])
        and height == int(video["height"])
        and round(fps) == int(video["fps"])
    )


def write_metadata(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prepare_loop_video(channel_name, source_path, force=False):
    library = ChannelLibrary(channel_name)
    profile = ensure_stream_profile()

    source_path = Path(source_path)
    output_path = build_video_output_path(library, source_path)
    metadata_path = library.loop_video_metadata_path(source_path)

    if output_path.exists() and not force:
        return {
            "ok": True,
            "skipped": True,
            "source": str(source_path),
            "output": str(output_path),
            "reason": "stream_ready already exists",
        }

    source_probe = ffprobe(source_path)
    source_stream = get_video_stream(source_probe)

    if not source_stream:
        raise RuntimeError(f"No video stream found: {source_path}")

    video = profile["video"]
    width = int(video["width"])
    height = int(video["height"])
    fps = int(video["fps"])
    keyframe = fps * int(video.get("keyframe_seconds", 2))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        str(video.get("preset", "veryfast")),
        "-crf",
        str(video.get("crf", 21)),
        "-b:v",
        str(video["bitrate"]),
        "-maxrate",
        str(video["maxrate"]),
        "-bufsize",
        str(video["bufsize"]),
        "-r",
        str(fps),
        "-g",
        str(keyframe),
        "-keyint_min",
        str(keyframe),
        "-sc_threshold",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = run_cmd(cmd)

    if result.returncode != 0:
        write_metadata(
            metadata_path,
            {
                "ok": False,
                "source": str(source_path),
                "output": str(output_path),
                "cmd": cmd,
                "stderr": result.stderr[-4000:],
                "stdout": result.stdout[-4000:],
            },
        )

        raise RuntimeError(result.stderr[-4000:] or result.stdout[-4000:])

    output_probe = ffprobe(output_path)

    metadata = {
        "ok": True,
        "source": str(source_path),
        "output": str(output_path),
        "profile": profile,
        "source_probe": source_probe,
        "output_probe": output_probe,
    }

    write_metadata(metadata_path, metadata)

    return {
        "ok": True,
        "skipped": False,
        "source": str(source_path),
        "output": str(output_path),
        "metadata": str(metadata_path),
    }


def prepare_channel_loop_videos(channel_name, force=False):
    library = ChannelLibrary(channel_name)

    results = []

    for source in library.list_original_loop_videos():
        # Do not process already prepared files again.
        if "stream_ready" in source.parts:
            continue

        results.append(
            prepare_loop_video(
                channel_name,
                source,
                force=force,
            )
        )

    return results


def prepare_all_channels(force=False):
    library_root = PROJECT_ROOT / "library"

    if not library_root.exists():
        return []

    results = []

    for channel_dir in sorted(library_root.iterdir()):
        if not channel_dir.is_dir():
            continue

        if not (channel_dir / "config.json").exists():
            continue

        channel_name = channel_dir.name

        results.append(
            {
                "channel": channel_name,
                "results": prepare_channel_loop_videos(channel_name, force=force),
            }
        )

    return results

def prepare_vod_loop_video(
    channel_name,
    profile_key,
    source_path,
    force=False,
):
    library = ChannelLibrary(channel_name)
    profile = ensure_stream_profile()

    source_path = Path(source_path)
    output_path = (
        library.vod_profile_loop_videos_ready_dir(
            profile_key
        )
        / output_name(source_path)
    )
    metadata_path = (
        library.vod_profile_loop_videos_metadata_dir(
            profile_key
        )
        / f"{source_path.name}.json"
    )

    if output_path.exists() and not force:
        return {
            "ok": True,
            "skipped": True,
            "source": str(source_path),
            "output": str(output_path),
            "reason": "stream_ready already exists",
        }

    source_probe = ffprobe(source_path)
    source_stream = get_video_stream(source_probe)

    if not source_stream:
        raise RuntimeError(
            f"No video stream found: {source_path}"
        )

    video = profile["video"]
    width = int(video["width"])
    height = int(video["height"])
    fps = int(video["fps"])
    keyframe = fps * int(
        video.get("keyframe_seconds", 2)
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    vf = (
        f"scale={width}:{height}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:"
        "(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        str(video.get("preset", "veryfast")),
        "-crf",
        str(video.get("crf", 21)),
        "-b:v",
        str(video["bitrate"]),
        "-maxrate",
        str(video["maxrate"]),
        "-bufsize",
        str(video["bufsize"]),
        "-r",
        str(fps),
        "-g",
        str(keyframe),
        "-keyint_min",
        str(keyframe),
        "-sc_threshold",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = run_cmd(cmd)

    if result.returncode != 0:
        write_metadata(
            metadata_path,
            {
                "ok": False,
                "source": str(source_path),
                "output": str(output_path),
                "cmd": cmd,
                "stderr": result.stderr[-4000:],
                "stdout": result.stdout[-4000:],
            },
        )
        raise RuntimeError(
            result.stderr[-4000:]
            or result.stdout[-4000:]
        )

    output_probe = ffprobe(output_path)
    metadata = {
        "ok": True,
        "source": str(source_path),
        "output": str(output_path),
        "profile": profile,
        "source_probe": source_probe,
        "output_probe": output_probe,
    }
    write_metadata(metadata_path, metadata)

    return {
        "ok": True,
        "skipped": False,
        "source": str(source_path),
        "output": str(output_path),
        "metadata": str(metadata_path),
    }


def prepare_vod_profile_loop_videos(
    channel_name,
    profile_key,
    force=False,
):
    library = ChannelLibrary(channel_name)
    results = []

    for source in (
        library.list_vod_original_loop_videos(
            profile_key
        )
    ):
        if "stream_ready" in source.parts:
            continue

        results.append(
            prepare_vod_loop_video(
                channel_name=channel_name,
                profile_key=profile_key,
                source_path=source,
                force=force,
            )
        )

    return results

