from pathlib import Path
import random


class MusicProvider:

    def __init__(self, config):

        self.config = config

        self.music_path = Path(
            "/opt/youtubefactory/library"
        ) / config["name"] / "music"

    def get_track(self):

        tracks = []

        for extension in (
            "*.mp3",
            "*.wav",
            "*.flac",
            "*.m4a",
        ):

            tracks.extend(self.music_path.glob(extension))
            tracks.extend(self.music_path.glob(extension.upper()))

        if not tracks:

            raise ValueError(
                f"Музыка не найдена: {self.music_path}"
            )

        return random.choice(tracks)