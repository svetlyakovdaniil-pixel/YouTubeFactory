from pathlib import Path
import shutil


class QueueService:

    def __init__(self, channel):

        self.channel = channel
        self.queue_dir = (
            Path("/opt/youtubefactory/queue")
            / channel
        )

        self.queue_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def list_videos(self):

        return sorted(
            [
                video
                for video in self.queue_dir.glob("*.mp4")
                if video.name != "active.mp4"
            ],
            key=lambda p: p.name,
        )

    def count(self):

        return len(self.list_videos())

    def add_video(self, video_path):

        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(video_path)

        number = self.count() + 1

        target = self.queue_dir / f"queued_{number:04d}.mp4"

        while target.exists():
            number += 1
            target = self.queue_dir / f"queued_{number:04d}.mp4"

        shutil.copy2(video_path, target)

        if str(video_path).startswith("/opt/youtubefactory/output/"):
            video_path.unlink()

        return target

    def pop_next(self):

        videos = self.list_videos()

        if not videos:
            return None

        active = self.queue_dir / "active.mp4"

        if active.exists():
            active.unlink()

        videos[0].rename(active)

        return active

    def delete_active(self):

        active = self.queue_dir / "active.mp4"

        if active.exists():
            active.unlink()

    def clear(self):

        for video in self.list_videos():
            video.unlink()

        self.delete_active()