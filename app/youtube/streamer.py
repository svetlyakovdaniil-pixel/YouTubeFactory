import subprocess
from pathlib import Path


class YouTubeStreamer:

    def stream_video(self, video_path, rtmp_url, stream_key):

        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Видео не найдено: {video_path}")

        full_rtmp_url = f"{rtmp_url}/{stream_key}"

        cmd = [
            "ffmpeg",
            "-re",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            "4500k",
            "-maxrate",
            "4500k",
            "-bufsize",
            "9000k",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "60",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "44100",
            "-f",
            "flv",
            full_rtmp_url,
        ]

        process = subprocess.Popen(cmd)

        return process