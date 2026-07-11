import shutil
import subprocess
from pathlib import Path
from datetime import datetime


class SceneService:

    def __init__(self, channel):

        self.channel = channel

        self.root = Path("/opt/youtubefactory/library") / channel

        self.source_dir = self.root / "source_images"
        self.inbox_dir = self.root / "inbox_images"
        self.scenes_dir = self.root / "scenes"
        self.rejected_dir = self.root / "rejected"

        self.overlays_dir = Path("/opt/youtubefactory/assets/overlays")

        self.stars_overlay = self.overlays_dir / "stars" / "stars_loop.mp4"
        self.dust_overlay = self.overlays_dir / "dust" / "dust_loop.mp4"
        self.fog_overlay = self.overlays_dir / "fog" / "fog_loop.mp4"

        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_dir.mkdir(parents=True, exist_ok=True)

    def list_source_images(self):

        images = []

        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            images.extend(self.source_dir.glob(ext))
            images.extend(self.source_dir.glob(ext.upper()))

        return sorted(images, key=lambda p: p.name)

    def list_inbox_images(self):

        images = []

        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            images.extend(self.inbox_dir.glob(ext))
            images.extend(self.inbox_dir.glob(ext.upper()))

        return sorted(images, key=lambda p: p.name)

    def list_scenes(self):

        return sorted(
            self.scenes_dir.glob("*.mp4"),
            key=lambda p: p.name,
        )

    def next_scene_path(self):

        number = len(self.list_scenes()) + 1

        while True:
            target = self.scenes_dir / f"scene_{number:04d}.mp4"

            if not target.exists():
                return target

            number += 1

    def _check_overlays(self):

        missing = []

        for path in [
            self.stars_overlay,
            self.dust_overlay,
            self.fog_overlay,
        ]:
            if not path.exists():
                missing.append(str(path))

        if missing:
            raise FileNotFoundError(
                "Missing overlays: " + ", ".join(missing)
            )

    def create_scene_from_image(
        self,
        image_path,
        duration=15,
        fps=30,
        delete_source=False,
    ):

        self._check_overlays()

        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(image_path)

        output = self.next_scene_path()

        width = 1920
        height = 1080

        filter_complex = (
            "[0:v]"
            "scale=2048:1152:force_original_aspect_ratio=increase,"
            "crop=2048:1152,"
            "zoompan="
            "z='1+0.008*on/(15*30)':"
            "x='round(iw/2-(iw/zoom/2))':"
            "y='round(ih/2-(ih/zoom/2))':"
            "d=450:"
            "s=1920x1080:"
            "fps=30,"
            "eq=contrast=1.04:saturation=1.08:brightness=-0.02,"
            "format=yuv420p"
            "[base];"

            "[1:v]"
            "scale=1920:1080,"
            "format=yuv420p,"
            "eq=brightness=-0.15"
            "[stars];"

            "[2:v]"
            "scale=1920:1080,"
            "format=yuv420p,"
            "eq=brightness=-0.25"
            "[dust];"

            "[3:v]"
            "scale=1920:1080,"
            "format=yuv420p,"
            "eq=brightness=-0.35"
            "[fog];"

            "[base][fog]"
            "blend=all_mode=screen:all_opacity=0.10"
            "[b1];"

            "[b1][dust]"
            "blend=all_mode=screen:all_opacity=0.18"
            "[b2];"

            "[b2][stars]"
            "blend=all_mode=screen:all_opacity=0.22,"
            "vignette=PI/8,"
            "noise=alls=1.2:allf=t+u,"
            "unsharp=5:5:0.4:5:5:0.0,"
            "format=yuv420p"
            "[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",

            "-loop",
            "1",
            "-t",
            str(duration),
            "-i",
            str(image_path),

            "-stream_loop",
            "-1",
            "-t",
            str(duration),
            "-i",
            str(self.stars_overlay),

            "-stream_loop",
            "-1",
            "-t",
            str(duration),
            "-i",
            str(self.dust_overlay),

            "-stream_loop",
            "-1",
            "-t",
            str(duration),
            "-i",
            str(self.fog_overlay),

            "-filter_complex",
            filter_complex,

            "-map",
            "[v]",

            "-r",
            str(fps),

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-pix_fmt",
            "yuv420p",

            "-movflags",
            "+faststart",

            str(output),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        if delete_source:
            image_path.unlink()

        return output

    def create_next_scene(self):

        images = self.list_source_images()

        if not images:
            images = self.list_inbox_images()

        if not images:
            return None

        return self.create_scene_from_image(
            image_path=images[0],
            delete_source=False,
        )

    def reject_image(self, image_path):

        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(image_path)

        target = (
            self.rejected_dir
            / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_path.name}"
        )

        shutil.move(str(image_path), str(target))

        return target