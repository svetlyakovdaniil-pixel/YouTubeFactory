import subprocess
import threading
import time
from pathlib import Path


class RadioStreamer:

    def __init__(self):
        self.tmp_dir = Path("/opt/youtubefactory/tmp/radio")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def write_audio_concat(self, playlist, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            for track in playlist["tracks"]:
                path = track["path"].replace("'", "'\\''")
                f.write(f"file '{path}'\n")

    def stream(self, playlist, rtmp_url, stream_key):
        audio_concat = self.tmp_dir / "audio_concat.txt"

        self.write_audio_concat(
            playlist=playlist,
            output_path=audio_concat,
        )

        full_rtmp_url = f"{rtmp_url}/{stream_key}"

        duration_seconds = int(playlist["target_seconds"])
        loop_video = playlist["loop_video"]

        cmd = [
            "ffmpeg",

            "-re",

            "-stream_loop",
            "-1",
            "-i",
            str(loop_video),

            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),

            "-t",
            str(duration_seconds),

            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

            "-c:v",
            "copy",

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-ar",
            "48000",

            "-f",
            "flv",

            full_rtmp_url,
        ]

        process = subprocess.Popen(cmd)

        stop_event = threading.Event()

        return {
            "process": process,
            "stop_event": stop_event,
            "audio_concat_file": str(audio_concat),
            "cmd": cmd,
        }

    def wait_for_process(self, process, stop_event=None):
        try:
            return process.wait()
        finally:
            if stop_event:
                stop_event.set()