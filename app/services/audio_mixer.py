import subprocess
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
TMP_ROOT = PROJECT_ROOT / "tmp" / "radio"


def safe_channel_name(channel_name):
    return (
        str(channel_name)
        .replace("/", "_")
        .replace("\\", "_")
        .strip()
    )


class AudioMixer:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.work_dir = (
            TMP_ROOT / safe_channel_name(channel_name)
        )
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def build_filter_script(
        self,
        tracks,
        crossfade_seconds,
        target_seconds,
    ):
        crossfade_seconds = float(crossfade_seconds)
        target_seconds = float(target_seconds)

        if not tracks:
            raise ValueError("Audio playlist is empty")

        if crossfade_seconds < 0:
            raise ValueError(
                "crossfade_seconds cannot be negative"
            )

        if target_seconds <= 0:
            raise ValueError(
                "target_seconds must be greater than zero"
            )

        lines = []

        for index, _track in enumerate(tracks):
            lines.append(
                f"[{index}:a:0]"
                "aresample=48000,"
                "aformat=sample_fmts=fltp:"
                "sample_rates=48000:"
                "channel_layouts=stereo,"
                "asetpts=PTS-STARTPTS"
                f"[track{index}]"
            )

        if len(tracks) == 1:
            current_label = "track0"
        else:
            current_label = "track0"

            for index in range(1, len(tracks)):
                output_label = f"mix{index}"

                lines.append(
                    f"[{current_label}]"
                    f"[track{index}]"
                    "acrossfade="
                    f"d={crossfade_seconds}:"
                    "c1=tri:"
                    "c2=tri"
                    f"[{output_label}]"
                )

                current_label = output_label

        lines.append(
            f"[{current_label}]"
            f"atrim=duration={target_seconds},"
            "asetpts=PTS-STARTPTS"
            "[aout]"
        )

        return ";\n".join(lines) + "\n"

    def render(
        self,
        playlist,
        output_path=None,
        target_seconds=None,
    ):
        tracks = playlist.get("tracks", [])

        if not tracks:
            raise ValueError("Playlist has no tracks")

        crossfade_seconds = float(
            playlist.get("crossfade_seconds", 3.0)
        )

        if target_seconds is None:
            target_seconds = float(
                playlist.get("target_seconds", 0)
            )

        if target_seconds <= 0:
            raise ValueError(
                f"Invalid target_seconds: {target_seconds}"
            )

        if output_path is None:
            output_path = self.work_dir / "mixed_audio.m4a"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        filter_path = self.work_dir / "crossfade_filter.txt"

        filter_text = self.build_filter_script(
            tracks=tracks,
            crossfade_seconds=crossfade_seconds,
            target_seconds=target_seconds,
        )

        filter_path.write_text(
            filter_text,
            encoding="utf-8",
        )

        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
        ]

        for track in tracks:
            command.extend(
                [
                    "-i",
                    str(track["path"]),
                ]
            )

        command.extend(
            [
                "-filter_complex_script",
                str(filter_path),
                "-map",
                "[aout]",
                "-map_metadata",
                "-1",
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Crossfade audio render failed\n\n"
                + result.stderr[-12000:]
            )

        return {
            "ok": True,
            "output_path": str(output_path),
            "filter_path": str(filter_path),
            "target_seconds": target_seconds,
            "crossfade_seconds": crossfade_seconds,
            "track_count": len(tracks),
            "command": command,
            "stderr": result.stderr[-4000:],
        }
