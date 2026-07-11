from pathlib import Path
import subprocess


class LiveService:

    def __init__(self):

        self.status_dir = Path("/opt/youtubefactory/runtime")

        self.status_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def start(self, channel):

        flag = self.status_dir / f"{channel}.running"

        if flag.exists():
            return

        flag.touch()

        subprocess.Popen(
            [
                "/opt/youtubefactory/venv/bin/python",
                "/opt/youtubefactory/workers/live_worker.py",
                channel,
            ]
        )

    def stop(self, channel):

        flag = self.status_dir / f"{channel}.running"

        if flag.exists():
            flag.unlink()

    def is_running(self, channel):

        return (
            self.status_dir /
            f"{channel}.running"
        ).exists()