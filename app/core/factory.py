from datetime import datetime

from app.core.config_manager import ConfigManager
from app.providers.image_provider import ImageProvider
from app.providers.music_provider import MusicProvider
from app.video.video_engine import VideoEngine


class YouTubeFactory:

    VERSION = "0.3.0"

    def run(self, channel: str):

        print("=" * 60)
        print("🚀 YouTube Factory")
        print("=" * 60)
        print(f"Version : {self.VERSION}")
        print(f"Started : {datetime.now()}")
        print()

        manager = ConfigManager()
        channels = manager.load_channels()

        config = None

        for item in channels:
            if item.get("name") == channel or item.get("id") == channel:
                config = item
                break

        if config is None:
            raise ValueError(f"Канал '{channel}' не найден.")

        image_provider = ImageProvider(config)
        music_provider = MusicProvider(config)

        images = image_provider.get_images()
        music = music_provider.get_track()

        print(f"Images found: {len(images)}")
        print(f"Music: {music.name}")
        print()

        engine = VideoEngine()

        return engine.create_video(
            images=images,
            music=music,
            config=config,
        )
