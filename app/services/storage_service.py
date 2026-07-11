import json
from pathlib import Path


class StorageService:

    BASE = Path("/opt/youtubefactory/data")

    def load(self, filename):

        file = self.BASE / filename

        if not file.exists():
            return []

        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, filename, data):

        file = self.BASE / filename

        with open(file, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4,
            )
