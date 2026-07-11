from pathlib import Path

import yaml

from app.core.config_validator import validate_channel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHANNELS_DIR = PROJECT_ROOT / "config" / "channels"


class ConfigManager:

    def __init__(self):
        self.channels = []

    def load_channels(self):

        self.channels.clear()

        for file in sorted(CHANNELS_DIR.glob("*.yaml")):

            with open(file, "r", encoding="utf-8") as f:
                channel = yaml.safe_load(f)

            validate_channel(channel)

            self.channels.append(channel)

        return self.channels