import json
import random
import subprocess
from pathlib import Path

from app.services.channel_library import ChannelLibrary


DEFAULT_CROSSFADE_SECONDS = 3.0


class RadioService:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(channel_name)

    def probe_duration(self, path):
        command = [
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
            command,
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

    def shuffled_tracks(self, music_files, previous=None):
        tracks = list(music_files)
        random.shuffle(tracks)

        if (
            previous is not None
            and len(tracks) > 1
            and tracks[0] == previous
        ):
            tracks[0], tracks[1] = tracks[1], tracks[0]

        return tracks

    def build_playlist(self):
        config = self.library.get_config()

        duration_hours = int(
            config.get("stream_duration_hours", 12)
        )

        target_seconds = duration_hours * 60 * 60

        crossfade_seconds = float(
            config.get(
                "crossfade_seconds",
                DEFAULT_CROSSFADE_SECONDS,
            )
        )

        if crossfade_seconds < 0:
            crossfade_seconds = DEFAULT_CROSSFADE_SECONDS

        music_files = self.library.list_music()
        loop_videos = self.library.list_loop_videos()

        if not music_files:
            raise ValueError(
                f"No music found for channel: {self.channel_name}"
            )

        if not loop_videos:
            raise ValueError(
                f"No loop videos found for channel: {self.channel_name}"
            )

        loop_video = random.choice(loop_videos)

        track_pool = self.shuffled_tracks(music_files)
        pool_index = 0
        previous_track = None

        playlist = []
        raw_total_seconds = 0.0
        mixed_total_seconds = 0.0

        while mixed_total_seconds < target_seconds:
            if pool_index >= len(track_pool):
                track_pool = self.shuffled_tracks(
                    music_files,
                    previous=previous_track,
                )
                pool_index = 0

            track = track_pool[pool_index]
            pool_index += 1

            duration = self.probe_duration(track)

            playlist.append(
                {
                    "path": str(track),
                    "title": self.clean_track_name(track),
                    "duration": duration,
                }
            )

            raw_total_seconds += duration

            if len(playlist) == 1:
                mixed_total_seconds += duration
            else:
                mixed_total_seconds += max(
                    duration - crossfade_seconds,
                    0.1,
                )

            previous_track = track

        data = {
            "channel": self.channel_name,
            "duration_hours": duration_hours,
            "target_seconds": target_seconds,
            "raw_total_seconds": raw_total_seconds,
            "total_seconds": mixed_total_seconds,
            "crossfade_seconds": crossfade_seconds,
            "loop_video": str(loop_video),
            "tracks": playlist,
        }

        playlist_path = (
            self.library.output_dir / "playlist.json"
        )

        playlist_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            playlist_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return data
