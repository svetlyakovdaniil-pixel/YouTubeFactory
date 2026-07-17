import json
import random
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.channel_library import ChannelLibrary


AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
}

FONT_PATH = (
    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans-Bold.ttf"
)


class VODVideoEngine:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(
            channel_name
        )

    def _run(self, command):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error = (
                result.stderr.strip()
                or result.stdout.strip()
            )
            raise RuntimeError(
                error
                or "FFmpeg command failed."
            )

        return result

    def _probe_duration(self, path):
        result = self._run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                (
                    "default=noprint_wrappers=1:"
                    "nokey=1"
                ),
                str(path),
            ]
        )

        try:
            duration = float(
                result.stdout.strip()
            )
        except (TypeError, ValueError):
            raise RuntimeError(
                "Не удалось определить "
                f"длительность файла: {path}"
            )

        if duration <= 0:
            raise RuntimeError(
                "Некорректная длительность "
                f"файла: {path}"
            )

        return duration

    def _format_timestamp(self, seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(
            seconds,
            3600,
        )
        minutes, secs = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{secs:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{secs:02d}"
        )

    def _escape_filter_text(self, value):
        value = str(value or "")
        value = value.replace(
            "\\",
            r"\\",
        )
        value = value.replace(
            ":",
            r"\:",
        )
        value = value.replace(
            "'",
            r"\'",
        )
        value = value.replace(
            "%",
            r"\%",
        )
        value = value.replace(
            ",",
            r"\,",
        )
        value = value.replace(
            "[",
            r"\[",
        )
        value = value.replace(
            "]",
            r"\]",
        )
        value = value.replace(
            "\n",
            " ",
        )

        return value

    def _select_duration_seconds(
        self,
        duration_minutes,
        minimum=60,
        maximum=120,
        allow_short_test=False,
    ):
        minimum = int(minimum)
        maximum = int(maximum)

        if duration_minutes is None:
            duration_minutes = random.randint(
                minimum,
                maximum,
            )
        else:
            duration_minutes = int(
                duration_minutes
            )

        if (
            not allow_short_test
            and (
                duration_minutes < minimum
                or duration_minutes > maximum
            )
        ):
            raise ValueError(
                "Длительность должна быть "
                f"от {minimum} до {maximum} минут."
            )

        if duration_minutes <= 0:
            raise ValueError(
                "Длительность должна быть "
                "больше нуля."
            )

        return duration_minutes * 60

    def _build_playlist(
        self,
        tracks,
        target_seconds,
        crossfade_seconds,
    ):
        if not tracks:
            raise RuntimeError(
                "Планировщик не передал "
                "ни одного VOD-трека."
            )

        prepared = []

        for item in tracks:
            path = Path(
                item.get("path", "")
            )

            if not path.exists():
                continue

            if (
                path.suffix.lower()
                not in AUDIO_EXTENSIONS
            ):
                continue

            try:
                duration = self._probe_duration(
                    path
                )
            except RuntimeError:
                continue

            prepared.append(
                {
                    "path": path,
                    "title": (
                        item.get("title")
                        or path.stem
                    ),
                    "vod_uses": int(
                        item.get(
                            "vod_uses",
                            0,
                        )
                        or 0
                    ),
                    "duration_seconds": duration,
                }
            )

        if not prepared:
            raise RuntimeError(
                "Нет исправных треков "
                "для VOD."
            )

        prepared.sort(
            key=lambda item: item[
                "vod_uses"
            ]
        )

        playlist = []
        elapsed = 0.0
        cycle = list(prepared)

        while elapsed < target_seconds:
            for item in cycle:
                if elapsed >= target_seconds:
                    break

                start_seconds = (
                    0.0
                    if not playlist
                    else max(
                        0.0,
                        elapsed
                        - crossfade_seconds,
                    )
                )

                playlist.append(
                    {
                        **item,
                        "start_seconds": (
                            start_seconds
                        ),
                    }
                )

                if len(playlist) == 1:
                    elapsed += item[
                        "duration_seconds"
                    ]
                else:
                    elapsed += (
                        item[
                            "duration_seconds"
                        ]
                        - crossfade_seconds
                    )

            random.shuffle(cycle)

        return playlist

    def _create_audio_mix(
        self,
        playlist,
        temp_dir,
        target_seconds,
        crossfade_seconds,
    ):
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-nostdin",
        ]

        for item in playlist:
            command.extend(
                [
                    "-i",
                    str(item["path"]),
                ]
            )

        filters = []

        for index, _ in enumerate(
            playlist
        ):
            filters.append(
                f"[{index}:a]"
                "aresample=48000,"
                "aformat=sample_fmts=fltp:"
                "sample_rates=48000:"
                "channel_layouts=stereo"
                f"[a{index}]"
            )

        current_label = "a0"

        for index in range(
            1,
            len(playlist),
        ):
            output_label = f"mix{index}"

            filters.append(
                f"[{current_label}]"
                f"[a{index}]"
                "acrossfade="
                f"d={crossfade_seconds}:"
                "c1=tri:c2=tri"
                f"[{output_label}]"
            )

            current_label = output_label

        audio_output = (
            temp_dir / "audio_mix.m4a"
        )

        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                f"[{current_label}]",
                "-t",
                str(target_seconds),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(audio_output),
            ]
        )

        self._run(command)

        return audio_output

    def _short_title(self, value, limit=34):
        title = " ".join(
            str(value or "").split()
        )

        if len(title) <= limit:
            return title

        return title[: limit - 1].rstrip() + "…"

    def _build_drawtext_filter(
        self,
        playlist,
        target_seconds,
    ):
        filters = [
            (
                "scale=1920:1080:"
                "force_original_aspect_ratio=decrease"
            ),
            (
                "pad=1920:1080:"
                "(ow-iw)/2:(oh-ih)/2"
            ),
            "fps=30",
            "format=yuv420p",
        ]

        channel_name = self._escape_filter_text(
            self.channel_name
        )

        for item in playlist:
            start = max(
                0.0,
                float(
                    item["start_seconds"]
                ),
            )
            end = min(
                float(target_seconds),
                start
                + float(
                    item[
                        "duration_seconds"
                    ]
                ),
            )

            if end <= start:
                continue

            show_start = start + 5.0
            show_end = end - 5.0

            if show_end <= show_start:
                continue

            title = self._escape_filter_text(
                self._short_title(
                    item["title"]
                )
            )
            enable = (
                f"'between(t,{show_start:.3f},"
                f"{show_end:.3f})'"
            )

            filters.append(
                "drawbox="
                "x=55:"
                "y=860:"
                "w=720:"
                "h=155:"
                "color=black@0.70:"
                "t=fill:"
                f"enable={enable}"
            )

            filters.append(
                "drawbox="
                "x=55:"
                "y=860:"
                "w=720:"
                "h=155:"
                "color=white@0.30:"
                "t=2:"
                f"enable={enable}"
            )

            filters.append(
                "drawbox="
                "x=55:"
                "y=860:"
                "w=9:"
                "h=155:"
                "color=white@0.95:"
                "t=fill:"
                f"enable={enable}"
            )

            filters.append(
                "drawtext="
                f"fontfile='{FONT_PATH}':"
                "text='♫  NOW PLAYING':"
                "fontcolor=white@0.78:"
                "fontsize=24:"
                "x=88:"
                "y=884:"
                "shadowcolor=black@0.9:"
                "shadowx=2:"
                "shadowy=2:"
                f"enable={enable}"
            )

            filters.append(
                "drawtext="
                f"fontfile='{FONT_PATH}':"
                f"text='{title}':"
                "fontcolor=white:"
                "fontsize=44:"
                "x=88:"
                "y=923:"
                "shadowcolor=black@0.95:"
                "shadowx=3:"
                "shadowy=3:"
                f"enable={enable}"
            )

            filters.append(
                "drawtext="
                f"fontfile='{FONT_PATH}':"
                f"text='{channel_name}':"
                "fontcolor=white@0.72:"
                "fontsize=25:"
                "x=88:"
                "y=977:"
                "shadowcolor=black@0.9:"
                "shadowx=2:"
                "shadowy=2:"
                f"enable={enable}"
            )

        return ",".join(filters)

    def _render_video(
        self,
        loop_video,
        audio_path,
        output_path,
        playlist,
        target_seconds,
        show_track_titles,
    ):
        if show_track_titles:
            video_filter = (
                self._build_drawtext_filter(
                    playlist,
                    target_seconds,
                )
            )
        else:
            video_filter = (
                "scale=1920:1080:"
                "force_original_aspect_ratio=decrease,"
                "pad=1920:1080:"
                "(ow-iw)/2:(oh-ih)/2,"
                "fps=30,"
                "format=yuv420p"
            )

        self._run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-nostdin",
                "-stream_loop",
                "-1",
                "-i",
                str(loop_video),
                "-i",
                str(audio_path),
                "-t",
                str(target_seconds),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "21",
                "-maxrate",
                "6000k",
                "-bufsize",
                "12000k",
                "-g",
                "60",
                "-keyint_min",
                "60",
                "-sc_threshold",
                "0",
                "-c:a",
                "copy",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
        )

    def _write_manifest(
        self,
        destination,
        output_path,
        loop_video,
        thumbnail,
        playlist,
        target_seconds,
        crossfade_seconds,
    ):
        tracks = []

        for item in playlist:
            if (
                item["start_seconds"]
                >= target_seconds
            ):
                continue

            tracks.append(
                {
                    "title": item["title"],
                    "timestamp": (
                        self._format_timestamp(
                            item[
                                "start_seconds"
                            ]
                        )
                    ),
                    "start_seconds": int(
                        item[
                            "start_seconds"
                        ]
                    ),
                    "source_file": str(
                        item["path"]
                    ),
                    "vod_uses_before": int(
                        item.get(
                            "vod_uses",
                            0,
                        )
                    ),
                }
            )

        manifest = {
            "channel": self.channel_name,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "output_file": str(
                output_path
            ),
            "loop_video": str(
                loop_video
            ),
            "thumbnail": (
                str(thumbnail)
                if thumbnail
                else ""
            ),
            "duration_seconds": (
                target_seconds
            ),
            "duration_minutes": (
                target_seconds // 60
            ),
            "crossfade_seconds": (
                crossfade_seconds
            ),
            "tracks": tracks,
        }

        with open(
            destination,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                manifest,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return manifest

    def create_from_plan(
        self,
        plan,
        duration_minutes=None,
        allow_short_test=False,
    ):
        if not plan.get("ready"):
            raise RuntimeError(
                "VOD-план не готов: "
                f"{plan.get('reason', '')}"
            )

        minimum = int(
            plan.get(
                "min_duration_minutes",
                60,
            )
        )
        maximum = int(
            plan.get(
                "max_duration_minutes",
                120,
            )
        )

        if duration_minutes is None:
            duration_minutes = int(
                plan.get(
                    "duration_minutes",
                    minimum,
                )
            )

        target_seconds = (
            self._select_duration_seconds(
                duration_minutes,
                minimum=minimum,
                maximum=maximum,
                allow_short_test=(
                    allow_short_test
                ),
            )
        )

        loop_video = Path(
            plan["loop_video"]
        )
        thumbnail = Path(
            plan["thumbnail"]
        )
        tracks = list(
            plan.get("tracks", [])
        )
        crossfade_seconds = int(
            plan.get(
                "crossfade_seconds",
                5,
            )
        )
        show_track_titles = bool(
            plan.get(
                "show_track_titles",
                True,
            )
        )

        if not loop_video.exists():
            raise FileNotFoundError(
                "VOD loop-видео не найдено: "
                f"{loop_video}"
            )

        if (
            loop_video.suffix.lower()
            not in VIDEO_EXTENSIONS
        ):
            raise ValueError(
                "Неподдерживаемый формат "
                f"видео: {loop_video.suffix}"
            )

        if "stream_ready" not in loop_video.parts:
            raise RuntimeError(
                "VOD Engine принимает только "
                "подготовленные stream_ready "
                f"loop-видео: {loop_video}"
            )

        if not thumbnail.exists():
            raise FileNotFoundError(
                "Превью не найдено: "
                f"{thumbnail}"
            )

        job_id = uuid.uuid4().hex
        temp_dir = (
            self.library.vod_tmp_dir
            / job_id
        )
        temp_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d_%H%M%S"
        )
        output_path = (
            self.library.vod_output_dir
            / (
                f"{timestamp}_"
                f"{target_seconds // 60}min.mp4"
            )
        )
        manifest_path = (
            self.library.vod_metadata_dir
            / f"{output_path.stem}.json"
        )

        state = self.library.get_vod_state()
        state.update(
            {
                "running": True,
                "stage": "rendering",
                "started_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "finished_at": "",
                "output_file": str(
                    output_path
                ),
                "youtube_video_id": "",
                "youtube_url": "",
                "last_error": "",
            }
        )
        self.library.save_vod_state(
            state
        )

        try:
            playlist = self._build_playlist(
                tracks=tracks,
                target_seconds=(
                    target_seconds
                ),
                crossfade_seconds=(
                    crossfade_seconds
                ),
            )

            audio_path = (
                self._create_audio_mix(
                    playlist=playlist,
                    temp_dir=temp_dir,
                    target_seconds=(
                        target_seconds
                    ),
                    crossfade_seconds=(
                        crossfade_seconds
                    ),
                )
            )

            self._render_video(
                loop_video=loop_video,
                audio_path=audio_path,
                output_path=output_path,
                playlist=playlist,
                target_seconds=(
                    target_seconds
                ),
                show_track_titles=(
                    show_track_titles
                ),
            )

            if (
                not output_path.exists()
                or output_path.stat().st_size
                == 0
            ):
                raise RuntimeError(
                    "FFmpeg не создал "
                    "итоговый VOD-файл."
                )

            manifest = self._write_manifest(
                destination=manifest_path,
                output_path=output_path,
                loop_video=loop_video,
                thumbnail=thumbnail,
                playlist=playlist,
                target_seconds=(
                    target_seconds
                ),
                crossfade_seconds=(
                    crossfade_seconds
                ),
            )

            state.update(
                {
                    "running": False,
                    "stage": "ready",
                    "finished_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "output_file": str(
                        output_path
                    ),
                    "last_error": "",
                }
            )
            self.library.save_vod_state(
                state
            )

            return {
                "output_path": output_path,
                "manifest_path": (
                    manifest_path
                ),
                "manifest": manifest,
            }

        except Exception as error:
            state.update(
                {
                    "running": False,
                    "stage": "error",
                    "finished_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "last_error": str(error),
                }
            )
            self.library.save_vod_state(
                state
            )
            raise

        finally:
            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )
