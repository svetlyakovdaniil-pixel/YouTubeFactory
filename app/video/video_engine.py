import random
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
import uuid


class VideoEngine:

    def create_video(self, images, music=None, config=None):

        output_dir = Path("/opt/youtubefactory/output")
        output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = Path("/opt/youtubefactory/tmp") / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4"
            output = output_dir / filename

            if not images:
                raise ValueError("Нет изображений для создания видео.")

            video_cfg = config.get("video", {}) if config else {}

            fps = int(video_cfg.get("fps", 30))
            image_duration = int(video_cfg.get("image_duration", 90))
            target_duration = int(video_cfg.get("target_duration", 900))

            width = 1920
            height = 1080

            scene_count = max(1, target_duration // image_duration)

            selected_images = list(images)
            random.shuffle(selected_images)

            while len(selected_images) < scene_count:
                extra = list(images)
                random.shuffle(extra)
                selected_images.extend(extra)

            selected_images = selected_images[:scene_count]

            scene_files = []

            for index, image in enumerate(selected_images):

                scene = temp_dir / f"scene_{index:04d}.mp4"

                move = random.choice([
                    "left_to_right",
                    "right_to_left",
                    "top_to_bottom",
                    "bottom_to_top",
                    "slow_center",
                ])

                if move == "left_to_right":
                    x_expr = f"(iw-ow)*t/{image_duration}"
                    y_expr = "(ih-oh)/2"

                elif move == "right_to_left":
                    x_expr = f"(iw-ow)*(1-t/{image_duration})"
                    y_expr = "(ih-oh)/2"

                elif move == "top_to_bottom":
                    x_expr = "(iw-ow)/2"
                    y_expr = f"(ih-oh)*t/{image_duration}"

                elif move == "bottom_to_top":
                    x_expr = "(iw-ow)/2"
                    y_expr = f"(ih-oh)*(1-t/{image_duration})"

                else:
                    x_expr = "(iw-ow)/2"
                    y_expr = "(ih-oh)/2"

                vf = (
                    "scale=2048:1152:force_original_aspect_ratio=increase,"
                    "crop=2048:1152,"
                    f"crop={width}:{height}:x='{x_expr}':y='{y_expr}',"
                    "noise=alls=2:allf=t+u,"
                    "vignette=PI/6,"
                    "eq=contrast=1.03:saturation=1.04,"
                    "fade=t=in:st=0:d=3,"
                    f"fade=t=out:st={image_duration - 3}:d=3,"
                    "format=yuv420p"
                )

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-loop", "1",
                    "-i", str(image),
                    "-t", str(image_duration),
                    "-vf", vf,
                    "-r", str(fps),
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    str(scene),
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

                scene_files.append(scene)

            concat_file = temp_dir / "scenes.txt"

            with open(concat_file, "w", encoding="utf-8") as f:
                for scene in scene_files:
                    f.write(f"file '{scene.resolve()}'\n")

            video_without_music = temp_dir / "video_without_music.mp4"

            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-c", "copy",
                    str(video_without_music),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            if music:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i", str(video_without_music),
                        "-stream_loop", "-1",
                        "-i", str(music),
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
                        "-movflags", "+faststart",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

            else:
                video_without_music.rename(output)

            print(f"Видео создано: {output}")
            return output

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)