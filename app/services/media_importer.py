import json
import shutil
import time
from pathlib import Path

from app.services.channel_library import ChannelLibrary, LIBRARY_ROOT
from app.services.media_pipeline import prepare_loop_video


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IGNORE_SUFFIXES = {".part", ".tmp", ".crdownload"}


class MediaImporter:

    def __init__(self, stable_seconds=8):
        self.stable_seconds = stable_seconds

    def channels(self):
        if not LIBRARY_ROOT.exists():
            return []

        return sorted(
            [item.name for item in LIBRARY_ROOT.iterdir() if item.is_dir()]
        )

    def is_stable(self, path):
        if path.suffix.lower() in IGNORE_SUFFIXES:
            return False

        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return False

        return age >= self.stable_seconds

    def media_type(self, path):
        suffix = path.suffix.lower()

        if suffix in AUDIO_EXTENSIONS:
            return "music"

        if suffix in VIDEO_EXTENSIONS:
            return "loop_videos"

        if suffix in IMAGE_EXTENSIONS:
            return "images"

        return "unknown"

    def unique_destination(self, target_dir, filename):
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = target_dir / filename

        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix

        for index in range(1, 1000):
            new_candidate = target_dir / f"{stem}_{index}{suffix}"

            if not new_candidate.exists():
                return new_candidate

        raise RuntimeError(f"Cannot create unique destination for {candidate}")

    def same_file_payload(self, source, destination):
        if not destination.exists():
            return False

        try:
            return source.stat().st_size == destination.stat().st_size
        except FileNotFoundError:
            return False

    def move_or_skip_duplicate(self, source, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        direct_target = target_dir / source.name

        if self.same_file_payload(source, direct_target):
            source.unlink()
            return {
                "moved": False,
                "skipped_duplicate": True,
                "path": str(direct_target),
            }

        destination = self.unique_destination(target_dir, source.name)
        shutil.move(str(source), str(destination))

        return {
            "moved": True,
            "skipped_duplicate": False,
            "path": str(destination),
        }

    def import_file(self, channel_name, source):
        library = ChannelLibrary(channel_name)
        source = Path(source)

        kind = self.media_type(source)

        if kind == "unknown":
            return {
                "ok": False,
                "channel": channel_name,
                "source": str(source),
                "error": "Unsupported file type",
            }

        if not self.is_stable(source):
            return {
                "ok": True,
                "channel": channel_name,
                "source": str(source),
                "skipped": True,
                "reason": "file is still being uploaded",
            }

        if kind == "music":
            move_result = self.move_or_skip_duplicate(source, library.music_dir)

            return {
                "ok": True,
                "channel": channel_name,
                "type": kind,
                "source": str(source),
                "destination": move_result["path"],
                "skipped_duplicate": move_result["skipped_duplicate"],
            }

        if kind == "images":
            move_result = self.move_or_skip_duplicate(source, library.images_dir)

            return {
                "ok": True,
                "channel": channel_name,
                "type": kind,
                "source": str(source),
                "destination": move_result["path"],
                "skipped_duplicate": move_result["skipped_duplicate"],
            }

        if kind == "loop_videos":
            move_result = self.move_or_skip_duplicate(source, library.loop_videos_original_dir)

            if move_result["skipped_duplicate"]:
                prepared_source = Path(move_result["path"])
            else:
                prepared_source = Path(move_result["path"])

            prepare_result = prepare_loop_video(channel_name, prepared_source)

            return {
                "ok": True,
                "channel": channel_name,
                "type": kind,
                "source": str(source),
                "destination": str(prepared_source),
                "stream_ready": prepare_result.get("output"),
                "metadata": prepare_result.get("metadata"),
                "skipped_duplicate": move_result["skipped_duplicate"],
                "prepare": prepare_result,
            }

    def import_channel(self, channel_name):
        library = ChannelLibrary(channel_name)
        results = []

        for source in library.list_incoming_files():
            try:
                result = self.import_file(channel_name, source)
                if result and not result.get("skipped"):
                    results.append(result)
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "channel": channel_name,
                        "source": str(source),
                        "error": str(exc),
                    }
                )

        return results

    def import_all(self):
        results = []

        for channel_name in self.channels():
            channel_results = self.import_channel(channel_name)

            if channel_results:
                results.append(
                    {
                        "channel": channel_name,
                        "results": channel_results,
                    }
                )

        return results


def print_results(results):
    if results:
        print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
