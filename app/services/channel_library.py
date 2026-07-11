import json
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"


class ChannelLibrary:

    def __init__(self, channel_name):

        self.channel_name = channel_name
        self.root = LIBRARY_ROOT / channel_name

        self.music_dir = self.root / "music"
        self.loop_videos_dir = self.root / "loop_videos"
        self.images_dir = self.root / "images"
        self.output_dir = self.root / "output"
        self.cache_dir = self.root / "cache"
        self.metadata_dir = self.root / "metadata"

        self.incoming_dir = self.root / "incoming"
        self.incoming_music_dir = self.incoming_dir / "music"
        self.incoming_loop_videos_dir = self.incoming_dir / "loop_videos"
        self.incoming_images_dir = self.incoming_dir / "images"

        # Media Pipeline v1.
        # Existing files in music/ and loop_videos/ continue to work.
        # New prepared media is stored in stream_ready/.
        self.music_original_dir = self.music_dir / "original"
        self.music_ready_dir = self.music_dir / "stream_ready"

        self.loop_videos_original_dir = self.loop_videos_dir / "original"
        self.loop_videos_ready_dir = self.loop_videos_dir / "stream_ready"

        self.loop_videos_metadata_dir = self.metadata_dir / "loop_videos"
        self.music_metadata_dir = self.metadata_dir / "music"

        self.config_path = self.root / "config.json"
        self.state_path = self.root / "state.json"

        self.ensure_dirs()

    def ensure_dirs(self):

        self.root.mkdir(parents=True, exist_ok=True)
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.loop_videos_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_music_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_loop_videos_dir.mkdir(parents=True, exist_ok=True)
        self.incoming_images_dir.mkdir(parents=True, exist_ok=True)

        self.music_original_dir.mkdir(parents=True, exist_ok=True)
        self.music_ready_dir.mkdir(parents=True, exist_ok=True)

        self.loop_videos_original_dir.mkdir(parents=True, exist_ok=True)
        self.loop_videos_ready_dir.mkdir(parents=True, exist_ok=True)

        self.loop_videos_metadata_dir.mkdir(parents=True, exist_ok=True)
        self.music_metadata_dir.mkdir(parents=True, exist_ok=True)

    def read_json(self, path, default):

        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, path, data):

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_config(self):

        return self.read_json(
            self.config_path,
            {
                "name": self.channel_name,
                "enabled": False,
                "stream_duration_hours": 12,
                "privacy": "unlisted",
                "title_template": f"{self.channel_name} Radio",
                "description": "",
            },
        )

    def save_config(self, config):

        self.write_json(self.config_path, config)

    def get_state(self):

        return self.read_json(
            self.state_path,
            {
                "running": False,
                "watch_url": "",
                "started_at": "",
                "stream_duration_hours": 12,
                "current_track": "",
                "track_index": 0,
                "last_error": "",
            },
        )

    def save_state(self, state):

        self.write_json(self.state_path, state)

    def _list_files(self, directory, extensions):

        files = []

        if not directory.exists():
            return files

        for ext in extensions:
            files.extend(directory.glob(ext))
            files.extend(directory.glob(ext.upper()))

        return sorted(
            [
                item
                for item in files
                if item.is_file()
            ],
            key=lambda p: p.name,
        )

    def _dedupe_paths(self, paths):

        result = []
        seen = set()

        for path in paths:
            key = str(path.resolve())

            if key in seen:
                continue

            seen.add(key)
            result.append(path)

        return result

    def list_music(self):

        extensions = ("*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac")

        ready = self._list_files(self.music_ready_dir, extensions)
        legacy = self._list_files(self.music_dir, extensions)
        original = self._list_files(self.music_original_dir, extensions)

        # For now music still supports legacy files directly.
        # If stream_ready audio exists, it is preferred but legacy still remains available.
        return self._dedupe_paths(ready + legacy + original)

    def list_ready_music(self):

        extensions = ("*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac")
        return self._list_files(self.music_ready_dir, extensions)

    def list_original_music(self):

        extensions = ("*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac")
        legacy = self._list_files(self.music_dir, extensions)
        original = self._list_files(self.music_original_dir, extensions)

        return self._dedupe_paths(legacy + original)

    def list_loop_videos(self):

        extensions = ("*.mp4", "*.mov", "*.webm", "*.mkv")

        ready = self._list_files(self.loop_videos_ready_dir, extensions)

        # Important: if prepared videos exist, use only them for streaming.
        # This keeps bitrate/FPS stable and avoids accidentally using huge originals.
        if ready:
            return ready

        legacy = self._list_files(self.loop_videos_dir, extensions)
        original = self._list_files(self.loop_videos_original_dir, extensions)

        return self._dedupe_paths(legacy + original)

    def list_ready_loop_videos(self):

        extensions = ("*.mp4", "*.mov", "*.webm", "*.mkv")
        return self._list_files(self.loop_videos_ready_dir, extensions)

    def list_original_loop_videos(self):

        extensions = ("*.mp4", "*.mov", "*.webm", "*.mkv")
        legacy = self._list_files(self.loop_videos_dir, extensions)
        original = self._list_files(self.loop_videos_original_dir, extensions)

        return self._dedupe_paths(legacy + original)

    def list_images(self):

        return self._list_files(
            self.images_dir,
            ("*.jpg", "*.jpeg", "*.png", "*.webp"),
        )

    def list_incoming_files(self):
        extensions = (
            "*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac",
            "*.mp4", "*.mov", "*.webm", "*.mkv",
            "*.jpg", "*.jpeg", "*.png", "*.webp",
        )

        files = []

        for folder in (
            self.incoming_dir,
            self.incoming_music_dir,
            self.incoming_loop_videos_dir,
            self.incoming_images_dir,
        ):
            files.extend(self._list_files(folder, extensions))

        return self._dedupe_paths(files)

    def media_metadata_path(self, media_type, source_path):

        safe_name = Path(source_path).name.replace("/", "_")
        return self.metadata_dir / media_type / f"{safe_name}.json"

    def loop_video_metadata_path(self, source_path):

        return self.media_metadata_path("loop_videos", source_path)

    def music_metadata_path(self, source_path):

        return self.media_metadata_path("music", source_path)
