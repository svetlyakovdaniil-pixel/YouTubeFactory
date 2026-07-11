from datetime import datetime

from app.core.config_manager import ConfigManager


def main():

    print("=" * 60)
    print("🚀 YouTube Factory")
    print("=" * 60)
    print()

    print("Started:", datetime.now())
    print()

    manager = ConfigManager()

    channels = manager.load_channels()

    print(f"Channels found: {len(channels)}")
    print()

    for channel in channels:
        print(f"• {channel['name']}")
        print(f"  id: {channel['id']}")
        print(f"  genre: {channel['genre']}")
        print(f"  source: {channel['video']['source']}")
        print()


if __name__ == "__main__":
    main()