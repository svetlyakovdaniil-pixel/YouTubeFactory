import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path("/opt/youtubefactory")
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.radio_service import RadioService


CHANNEL = "Cosmic Slumber"

OUTPUT = PROJECT_ROOT / "output" / "radio_test_60s.mp4"

TMP_DIR = PROJECT_ROOT / "tmp" / "radio_test"

FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def write_audio_concat(playlist, output_path):

    with open(output_path, "w", encoding="utf-8") as f:

        for track in playlist["tracks"][:3]:

            path = track["path"].replace("'", "'\\''")

            f.write(f"file '{path}'\n")


def write_now_playing(text_path, playlist):

    first_track = playlist["tracks"][0]["title"]

    text = f"♪ {first_track}\n{playlist['channel']} Radio"

    with open(text_path, "w", encoding="utf-8") as f:

        f.write(text)


def main():

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    service = RadioService(CHANNEL)

    playlist = service.build_playlist()

    audio_concat = TMP_DIR / "audio_concat.txt"

    now_playing = TMP_DIR / "now_playing.txt"

    write_audio_concat(
        playlist,
        audio_concat,
    )

    write_now_playing(
        now_playing,
        playlist,
    )

    vf = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "fps=30,"
        "drawtext="
        f"fontfile='{FONT_FILE}':"
        f"textfile='{now_playing}':"
        "reload=1:"
        "fontcolor=white:"
        "fontsize=38:"
        "line_spacing=10:"
        "x=50:"
        "y=h-th-70:"
        "box=1:"
        "boxcolor=black@0.38:"
        "boxborderw=20"
    )

    cmd = [
        "ffmpeg",

        "-y",

        "-stream_loop",
        "-1",
        "-i",
        playlist["loop_video"],

        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(audio_concat),

        "-t",
        "60",

        "-vf",
        vf,

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "libx264",

        "-preset",
        "ultrafast",

        "-tune",
        "zerolatency",

        "-b:v",
        "5000k",

        "-maxrate",
        "5000k",

        "-bufsize",
        "10000k",

        "-pix_fmt",
        "yuv420p",

        "-g",
        "60",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-ar",
        "44100",

        "-shortest",

        str(OUTPUT),
    ]

    print()
    print("Rendering test video 1080p/30fps ultrafast...")
    print()
    print("Output:", OUTPUT)
    print()

    result = subprocess.run(cmd)

    if result.returncode != 0:

        raise RuntimeError("FFmpeg render failed")

    print()
    print("Done:", OUTPUT)
    print()


if __name__ == "__main__":

    main()