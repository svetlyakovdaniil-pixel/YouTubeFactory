from pathlib import Path
import subprocess


CACHE_DIR = Path("/opt/youtubefactory/cache/images")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def prepare_image(image: Path) -> Path:

    cached = CACHE_DIR / f"{image.stem}.jpg"

    if cached.exists():
        return cached

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(image),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-q:v",
            "2",
            str(cached),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return cached