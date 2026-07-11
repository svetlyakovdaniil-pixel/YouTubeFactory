import subprocess


class VideoService:

    def create(self, channel):

        subprocess.run(
            [
                "python3",
                "-c",
                (
                    "from app.pipeline import create_video;"
                    f"create_video('{channel}')"
                ),
            ],
            cwd="/opt/youtubefactory",
            check=True,
        )

        return "/opt/youtubefactory/output/video.mp4"
