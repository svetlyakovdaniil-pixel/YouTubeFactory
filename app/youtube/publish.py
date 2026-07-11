import random
from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.services.ffmpeg_engine import FFmpegEngine
from app.youtube.live_stream import YouTubeLiveStream


PROJECT_ROOT = Path("/opt/youtubefactory")
TMP_ROOT = PROJECT_ROOT / "tmp" / "radio"


class Publisher:
    def pick_thumbnail(self, channel_name):
        library = ChannelLibrary(channel_name)
        valid = []

        for image in library.list_images():
            if image.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                continue
            try:
                if image.stat().st_size <= 2 * 1024 * 1024:
                    valid.append(image)
            except Exception:
                continue

        return random.choice(valid) if valid else None

    def write_audio_concat(self, channel_name, playlist):
        work_dir = TMP_ROOT / str(channel_name).replace("/", "_")
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / "audio_concat.txt"

        lines = []
        for track in playlist.get("tracks", []):
            audio_path = str(track.get("path", "")).replace("'", "'\\''")
            lines.append(f"file '{audio_path}'")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def build_ffmpeg_command(
        self,
        loop_video,
        audio_concat,
        rtmp_url,
        duration_seconds,
    ):
        duration_seconds = int(duration_seconds)
        if duration_seconds <= 0:
            raise ValueError(
                f"Invalid stream duration: {duration_seconds} seconds"
            )

        return [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            str(loop_video),
            "-re",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),
            "-t",
            str(duration_seconds),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-f",
            "flv",
            rtmp_url,
        ]

    def create_radio_event(self, channel_name, title, description=""):
        thumbnail = self.pick_thumbnail(channel_name)
        event = YouTubeLiveStream(channel_name).create_live_event(
            title=title,
            description=description,
            thumbnail_path=thumbnail,
        )
        event["thumbnail_path"] = str(thumbnail) if thumbnail else ""
        return event

    def start_radio_ffmpeg(self, channel_name, playlist, event):
        loop_video = playlist.get("loop_video")

        if not loop_video:
            loop_videos = ChannelLibrary(channel_name).list_loop_videos()
            if not loop_videos:
                raise ValueError(
                    f"No loop videos found for channel: {channel_name}"
                )
            loop_video = random.choice(loop_videos)

        loop_video = Path(loop_video)
        duration_seconds = int(playlist.get("target_seconds", 0))
        if duration_seconds <= 0:
            raise ValueError(
                f"Playlist has invalid target_seconds: {duration_seconds}"
            )

        audio_concat = self.write_audio_concat(channel_name, playlist)
        rtmp_url = f"{event['rtmp_url']}/{event['stream_key']}"
        command = self.build_ffmpeg_command(
            loop_video=loop_video,
            audio_concat=audio_concat,
            rtmp_url=rtmp_url,
            duration_seconds=duration_seconds,
        )

        engine = FFmpegEngine(channel_name)
        ffmpeg_process = engine.start(
            command,
            context={
                "BROADCAST_ID": event.get("broadcast_id", ""),
                "STREAM_ID": event.get("stream_id", ""),
                "LOOP_VIDEO": loop_video,
                "AUDIO_CONCAT": audio_concat,
                "THUMBNAIL": event.get("thumbnail_path", ""),
                "DURATION_SECONDS": duration_seconds,
            },
        )

        result = dict(event)
        result.update(
            {
                "ffmpeg_engine": engine,
                "ffmpeg_process": ffmpeg_process,
                "process": ffmpeg_process.process,
                "loop_video": str(loop_video),
                "audio_concat": str(audio_concat),
                "duration_seconds": duration_seconds,
                "ffmpeg_command": command,
            }
        )
        return result

    def publish_radio(self, channel_name, playlist, title, description=""):
        event = self.create_radio_event(
            channel_name=channel_name,
            title=title,
            description=description,
        )
        return self.start_radio_ffmpeg(
            channel_name=channel_name,
            playlist=playlist,
            event=event,
        )

    def publish(
        self,
        channel_name,
        video_path,
        title,
        description="",
        thumbnail_path=None,
    ):
        live = YouTubeLiveStream(channel_name)
        event = live.create_live_event(
            title=title,
            description=description,
            thumbnail_path=thumbnail_path,
        )
        rtmp_url = f"{event['rtmp_url']}/{event['stream_key']}"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-f",
            "flv",
            rtmp_url,
        ]

        engine = FFmpegEngine(channel_name)
        ffmpeg_process = engine.start(
            command,
            context={"VIDEO_PATH": video_path},
        )
        event.update(
            {
                "ffmpeg_engine": engine,
                "ffmpeg_process": ffmpeg_process,
                "process": ffmpeg_process.process,
                "ffmpeg_command": command,
            }
        )
        return event
