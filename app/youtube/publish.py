import random
from pathlib import Path

from app.services.audio_mixer import AudioMixer
from app.services.channel_library import ChannelLibrary
from app.services.ffmpeg_engine import FFmpegEngine
from app.youtube.live_stream import YouTubeLiveStream


PROJECT_ROOT = Path("/opt/youtubefactory")


class Publisher:
    def pick_thumbnail(self, channel_name):
        library = ChannelLibrary(channel_name)
        images = library.list_images()

        valid = []

        for image in images:
            suffix = image.suffix.lower()

            if suffix not in [".jpg", ".jpeg", ".png"]:
                continue

            try:
                if image.stat().st_size <= 2 * 1024 * 1024:
                    valid.append(image)
            except Exception:
                continue

        if not valid:
            return None

        return random.choice(valid)

    def build_ffmpeg_command(
        self,
        loop_video,
        mixed_audio,
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
            "-i",
            str(mixed_audio),
            "-t",
            str(duration_seconds),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-f",
            "flv",
            rtmp_url,
        ]

    def publish_radio(
        self,
        channel_name,
        playlist,
        title,
        description="",
    ):
        library = ChannelLibrary(channel_name)

        loop_video = playlist.get("loop_video")

        if not loop_video:
            loop_videos = library.list_loop_videos()

            if not loop_videos:
                raise ValueError(
                    f"No loop videos found for channel: {channel_name}"
                )

            loop_video = random.choice(loop_videos)

        loop_video = Path(loop_video)

        duration_seconds = int(
            playlist.get("target_seconds", 0)
        )

        if duration_seconds <= 0:
            raise ValueError(
                f"Playlist has invalid target_seconds: {duration_seconds}"
            )

        mixer = AudioMixer(channel_name)

        mixed_result = mixer.render(
            playlist=playlist,
            target_seconds=duration_seconds,
        )

        mixed_audio = Path(
            mixed_result["output_path"]
        )

        thumbnail = self.pick_thumbnail(channel_name)

        live = YouTubeLiveStream(channel_name)

        event = live.create_live_event(
            title=title,
            description=description,
            thumbnail_path=thumbnail,
        )

        rtmp_url = (
            f"{event['rtmp_url']}/{event['stream_key']}"
        )

        command = self.build_ffmpeg_command(
            loop_video=loop_video,
            mixed_audio=mixed_audio,
            rtmp_url=rtmp_url,
            duration_seconds=duration_seconds,
        )

        engine = FFmpegEngine(channel_name)

        ffmpeg_process = engine.start(
            command,
            context={
                "LOOP_VIDEO": loop_video,
                "MIXED_AUDIO": mixed_audio,
                "THUMBNAIL": thumbnail,
                "DURATION_SECONDS": duration_seconds,
                "CROSSFADE_SECONDS": playlist.get(
                    "crossfade_seconds",
                    3.0,
                ),
            },
        )

        event["ffmpeg_engine"] = engine
        event["ffmpeg_process"] = ffmpeg_process
        event["process"] = ffmpeg_process.process
        event["loop_video"] = str(loop_video)
        event["mixed_audio"] = str(mixed_audio)
        event["thumbnail_path"] = (
            str(thumbnail) if thumbnail else ""
        )
        event["duration_seconds"] = duration_seconds
        event["crossfade_seconds"] = playlist.get(
            "crossfade_seconds",
            3.0,
        )
        event["ffmpeg_command"] = command

        return event

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

        rtmp_url = (
            f"{event['rtmp_url']}/{event['stream_key']}"
        )

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
            context={
                "VIDEO_PATH": video_path,
            },
        )

        event["ffmpeg_engine"] = engine
        event["ffmpeg_process"] = ffmpeg_process
        event["process"] = ffmpeg_process.process
        event["ffmpeg_command"] = command

        return event
