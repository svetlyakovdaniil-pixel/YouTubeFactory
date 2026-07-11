from pathlib import Path
import yaml


class ChannelService:

    def __init__(self):

        self.channels_dir = Path("/opt/youtubefactory/channels")

    def get_all(self):

        channels = []

        for file in sorted(self.channels_dir.glob("*.yaml")):

            with open(file, "r", encoding="utf-8") as f:

                channels.append(yaml.safe_load(f))

        return channels

    def get(self, name):

        for channel in self.get_all():

            if channel["name"] == name:

                return channel

        return None