import json
import random
import subprocess
from pathlib import Path

from app.services.channel_library import ChannelLibrary


class RadioService:

    def __init__(self, channel_name):

        self.channel_name = channel_name
        self.library = ChannelLibrary(channel_name)

    def probe_duration(self, path):

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return float(result.stdout.strip())

    def clean_track_name(self, path):

        name = Path(path).stem

        replacements = [
            "(промт0.1)",
            "(промт0)",
            "(промт1.1)",
            "(промт1)",
            "(промт2.1)",
            "(промт2)",
            "(промт3.1)",
            "(промт3)",
            "(промт4.1)",
            "(промт4)",
            "(промт5.1)",
            "(промт5)",
            "(промт6.1)",
            "(промт6)",
            "(промт7.1)",
            "(промт7)",
            "(промт8.1)",
            "(промт8)",
            "(промт9.1)",
            "(промт9)",
            "(промт10.1)",
            "(промт10)",
        ]

        for item in replacements:
            name = name.replace(item, "")

        return " ".join(name.split()).strip()

    def build_playlist(self):

        config = self.library.get_config()

        duration_hours = int(config.get("stream_duration_hours", 12))
        target_seconds = duration_hours * 60 * 60

        music_files = self.library.list_music()
        loop_videos = self.library.list_loop_videos()

        if not music_files:
            raise ValueError(f"No music found for channel: {self.channel_name}")

        if not loop_videos:
            raise ValueError(f"No loop videos found for channel: {self.channel_name}")

        loop_video = random.choice(loop_videos)

        tracks = music_files[:]
        random.shuffle(tracks)

        playlist = []
        total_seconds = 0
        track_index = 0

        while total_seconds < target_seconds:

            track = tracks[track_index % len(tracks)]
            duration = self.probe_duration(track)

            playlist.append(
                {
                    "path": str(track),
                    "title": self.clean_track_name(track),
                    "duration": duration,
                }
            )

            total_seconds += duration
            track_index += 1

            if track_index % len(tracks) == 0:
                random.shuffle(tracks)

        data = {
            "channel": self.channel_name,
            "duration_hours": duration_hours,
            "target_seconds": target_seconds,
            "total_seconds": total_seconds,
            "loop_video": str(loop_video),
            "tracks": playlist,
        }

        playlist_path = self.library.output_dir / "playlist.json"

        with open(playlist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return data