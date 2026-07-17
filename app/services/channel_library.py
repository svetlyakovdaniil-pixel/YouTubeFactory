import json
import re
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"

WEEK_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

NOLYRICS_DEFAULT_SCHEDULE = {
    "monday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "Lo-Fi Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best Lo-Fi Hip-Hop Beats of the Week",
            "Lo-Fi Hip-Hop Instrumentals for Late Night Vibes",
            "Smooth Lo-Fi Hip-Hop Beats Mix",
        ],
        "description_template": (
            "A weekly selection of Lo-Fi Hip-Hop instrumentals. "
            "Relaxed beats, smooth textures and laid-back rhythms.\n\n"
            "{tracklist}"
        ),
        "profile_key": "lo-fi-hip-hop",
    },
    "tuesday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "West Coast Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best West Coast Hip-Hop Beats of the Week",
            "West Coast Hip-Hop Instrumentals Mix",
            "Classic West Coast Beats for Cruising",
        ],
        "description_template": (
            "A weekly West Coast Hip-Hop instrumental mix with smooth basslines, "
            "laid-back drums and classic coastal energy.\n\n"
            "{tracklist}"
        ),
        "profile_key": "west-coast-hip-hop",
    },
    "wednesday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "Chill Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best Chill Hip-Hop Beats of the Week",
            "Chill Hip-Hop Instrumentals for Relaxing",
            "Smooth Chill Hip-Hop Beats Mix",
        ],
        "description_template": (
            "A weekly Chill Hip-Hop instrumental selection for relaxing, "
            "working and late-night listening.\n\n"
            "{tracklist}"
        ),
        "profile_key": "chill-hip-hop",
    },
    "thursday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "East Coast Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best East Coast Hip-Hop Beats of the Week",
            "East Coast Hip-Hop Instrumentals Mix",
            "Raw East Coast Beats and Boom Bap Instrumentals",
        ],
        "description_template": (
            "A weekly East Coast Hip-Hop instrumental mix with raw drums, "
            "dusty samples and classic city atmosphere.\n\n"
            "{tracklist}"
        ),
        "profile_key": "east-coast-hip-hop",
    },
    "friday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "Jazz Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best Jazz Hip-Hop Beats of the Week",
            "Jazz Hip-Hop Instrumentals Mix",
            "Smooth Jazz Rap Beats for Late Night Listening",
        ],
        "description_template": (
            "A weekly Jazz Hip-Hop instrumental mix with warm chords, "
            "dusty drums and smooth melodic samples.\n\n"
            "{tracklist}"
        ),
        "profile_key": "jazz-hip-hop",
    },
    "saturday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "Underground Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best Underground Hip-Hop Beats of the Week",
            "Underground Hip-Hop Instrumentals Mix",
            "Raw Underground Beats for Freestyle Sessions",
        ],
        "description_template": (
            "A weekly Underground Hip-Hop instrumental selection with raw drums, "
            "dark samples and independent street energy.\n\n"
            "{tracklist}"
        ),
        "profile_key": "underground-hip-hop",
    },
    "sunday": {
        "enabled": True,
        "genre": "Hip-Hop",
        "subgenre": "Old School Hip-Hop",
        "min_duration_minutes": 60,
        "max_duration_minutes": 120,
        "title_templates": [
            "Best Old School Hip-Hop Beats of the Week",
            "Old School Hip-Hop Instrumentals Mix",
            "Classic 90s Style Hip-Hop Beats",
        ],
        "description_template": (
            "A weekly Old School Hip-Hop instrumental mix inspired by classic "
            "golden-era drums, samples and timeless grooves.\n\n"
            "{tracklist}"
        ),
        "profile_key": "old-school-hip-hop",
    },
}


def empty_schedule():
    return {
        day: {
            "enabled": False,
            "genre": "",
            "subgenre": "",
            "min_duration_minutes": 60,
            "max_duration_minutes": 120,
            "title_templates": [],
            "description_template": "",
            "profile_key": "",
        }
        for day in WEEK_DAYS
    }


class ChannelLibrary:

    def __init__(self, channel_name):

        self.channel_name = channel_name
        self.root = LIBRARY_ROOT / channel_name

        self.music_dir = self.root / "music"
        self.images_dir = self.root / "images"
        self.cache_dir = self.root / "cache"
        self.metadata_dir = self.root / "metadata"

        self.loop_videos_dir = self.root / "loop_videos"
        self.output_dir = self.root / "output"

        self.incoming_dir = self.root / "incoming"
        self.incoming_music_dir = self.incoming_dir / "music"
        self.incoming_loop_videos_dir = self.incoming_dir / "loop_videos"
        self.incoming_images_dir = self.incoming_dir / "images"

        self.music_original_dir = self.music_dir / "original"
        self.music_ready_dir = self.music_dir / "stream_ready"

        self.loop_videos_original_dir = self.loop_videos_dir / "original"
        self.loop_videos_ready_dir = self.loop_videos_dir / "stream_ready"

        self.loop_videos_metadata_dir = self.metadata_dir / "loop_videos"
        self.music_metadata_dir = self.metadata_dir / "music"

        self.vod_dir = self.root / "vod"
        self.vod_loop_videos_dir = self.vod_dir / "loop_videos"
        self.vod_thumbnails_dir = self.vod_dir / "thumbnails"
        self.vod_output_dir = self.vod_dir / "output"
        self.vod_history_dir = self.vod_dir / "history"
        self.vod_metadata_dir = self.vod_dir / "metadata"
        self.vod_tmp_dir = self.vod_dir / "tmp"
        self.vod_profiles_dir = self.vod_dir / "profiles"

        self.vod_config_path = self.vod_dir / "config.json"
        self.vod_state_path = self.vod_dir / "state.json"
        self.vod_history_path = self.vod_history_dir / "publications.json"

        self.config_path = self.root / "config.json"
        self.state_path = self.root / "state.json"

        self.ensure_dirs()

    def ensure_dirs(self):

        directories = (
            self.root,
            self.music_dir,
            self.loop_videos_dir,
            self.images_dir,
            self.output_dir,
            self.cache_dir,
            self.metadata_dir,
            self.incoming_dir,
            self.incoming_music_dir,
            self.incoming_loop_videos_dir,
            self.incoming_images_dir,
            self.music_original_dir,
            self.music_ready_dir,
            self.loop_videos_original_dir,
            self.loop_videos_ready_dir,
            self.loop_videos_metadata_dir,
            self.music_metadata_dir,
            self.vod_dir,
            self.vod_loop_videos_dir,
            self.vod_thumbnails_dir,
            self.vod_output_dir,
            self.vod_history_dir,
            self.vod_metadata_dir,
            self.vod_tmp_dir,
            self.vod_profiles_dir,
        )

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def read_json(self, path, default):

        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def write_json(self, path, data):

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

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

    def _default_vod_config(self):

        schedule = (
            NOLYRICS_DEFAULT_SCHEDULE
            if self.channel_name == "NoLyricsGroove"
            else empty_schedule()
        )

        return {
            "enabled": False,
            "privacy": "public",
            "timezone": "Asia/Almaty",
            "publish_time": "12:00",
            "delete_output_after_upload": True,
            "crossfade_seconds": 5,
            "show_track_titles": True,
            "track_title_position": "bottom_left",
            "weekly_schedule": schedule,
        }

    def get_vod_config(self):

        default = self._default_vod_config()
        config = self.read_json(
            self.vod_config_path,
            default,
        )

        config.setdefault("enabled", False)
        config.setdefault("privacy", "public")
        config.setdefault("timezone", "Asia/Almaty")
        config.setdefault("publish_time", "12:00")
        config.setdefault(
            "delete_output_after_upload",
            True,
        )
        config.setdefault("crossfade_seconds", 5)
        config.setdefault("show_track_titles", True)
        config.setdefault(
            "track_title_position",
            "bottom_left",
        )
        config.setdefault(
            "weekly_schedule",
            default["weekly_schedule"],
        )

        for day in WEEK_DAYS:
            config["weekly_schedule"].setdefault(
                day,
                default["weekly_schedule"][day],
            )

        return config

    def save_vod_config(self, config):
        self.write_json(self.vod_config_path, config)

    def get_vod_state(self):

        return self.read_json(
            self.vod_state_path,
            {
                "running": False,
                "stage": "idle",
                "started_at": "",
                "finished_at": "",
                "output_file": "",
                "youtube_video_id": "",
                "youtube_url": "",
                "last_error": "",
            },
        )

    def save_vod_state(self, state):
        self.write_json(self.vod_state_path, state)

    def get_vod_history(self):
        return self.read_json(self.vod_history_path, [])

    def save_vod_history(self, history):
        self.write_json(self.vod_history_path, history)

    def append_vod_history(self, item):

        history = self.get_vod_history()
        history.append(item)
        self.save_vod_history(history)

    def slugify(self, value):

        value = str(value or "").strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")

        return value or "profile"

    def vod_profile_dir(self, profile_key):

        return (
            self.vod_profiles_dir
            / self.slugify(profile_key)
        )

    def vod_profile_loop_videos_dir(
        self,
        profile_key,
    ):

        directory = (
            self.vod_profile_dir(profile_key)
            / "loop_videos"
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory

    def vod_profile_loop_videos_original_dir(
        self,
        profile_key,
    ):

        directory = (
            self.vod_profile_loop_videos_dir(
                profile_key
            )
            / "original"
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory

    def vod_profile_loop_videos_ready_dir(
        self,
        profile_key,
    ):

        directory = (
            self.vod_profile_loop_videos_dir(
                profile_key
            )
            / "stream_ready"
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory

    def vod_profile_loop_videos_metadata_dir(
        self,
        profile_key,
    ):

        directory = (
            self.vod_profile_dir(profile_key)
            / "metadata"
            / "loop_videos"
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory

    def vod_profile_thumbnails_dir(
        self,
        profile_key,
    ):

        directory = (
            self.vod_profile_dir(profile_key)
            / "thumbnails"
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        return directory

    def ensure_vod_profile(self, profile_key):

        loop_dir = (
            self.vod_profile_loop_videos_dir(
                profile_key
            )
        )
        loop_original_dir = (
            self.vod_profile_loop_videos_original_dir(
                profile_key
            )
        )
        loop_ready_dir = (
            self.vod_profile_loop_videos_ready_dir(
                profile_key
            )
        )
        loop_metadata_dir = (
            self.vod_profile_loop_videos_metadata_dir(
                profile_key
            )
        )
        thumbnail_dir = (
            self.vod_profile_thumbnails_dir(
                profile_key
            )
        )

        return {
            "profile_key": self.slugify(
                profile_key
            ),
            "loop_videos_dir": loop_dir,
            "loop_videos_original_dir": loop_original_dir,
            "loop_videos_ready_dir": loop_ready_dir,
            "loop_videos_metadata_dir": loop_metadata_dir,
            "thumbnails_dir": thumbnail_dir,
        }

    def _list_files(self, directory, extensions):

        files = []

        if not directory.exists():
            return files

        for extension in extensions:
            files.extend(
                directory.glob(extension)
            )
            files.extend(
                directory.glob(
                    extension.upper()
                )
            )

        return sorted(
            [
                item
                for item in files
                if item.is_file()
            ],
            key=lambda path: path.name,
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

        extensions = (
            "*.mp3",
            "*.wav",
            "*.m4a",
            "*.aac",
            "*.flac",
        )

        ready = self._list_files(
            self.music_ready_dir,
            extensions,
        )
        legacy = self._list_files(
            self.music_dir,
            extensions,
        )
        original = self._list_files(
            self.music_original_dir,
            extensions,
        )

        return self._dedupe_paths(
            ready + legacy + original
        )

    def list_ready_music(self):

        return self._list_files(
            self.music_ready_dir,
            (
                "*.mp3",
                "*.wav",
                "*.m4a",
                "*.aac",
                "*.flac",
            ),
        )

    def list_original_music(self):

        extensions = (
            "*.mp3",
            "*.wav",
            "*.m4a",
            "*.aac",
            "*.flac",
        )

        legacy = self._list_files(
            self.music_dir,
            extensions,
        )
        original = self._list_files(
            self.music_original_dir,
            extensions,
        )

        return self._dedupe_paths(
            legacy + original
        )

    def list_loop_videos(self):

        extensions = (
            "*.mp4",
            "*.mov",
            "*.webm",
            "*.mkv",
        )

        ready = self._list_files(
            self.loop_videos_ready_dir,
            extensions,
        )

        if ready:
            return ready

        legacy = self._list_files(
            self.loop_videos_dir,
            extensions,
        )
        original = self._list_files(
            self.loop_videos_original_dir,
            extensions,
        )

        return self._dedupe_paths(
            legacy + original
        )

    def list_ready_loop_videos(self):

        return self._list_files(
            self.loop_videos_ready_dir,
            (
                "*.mp4",
                "*.mov",
                "*.webm",
                "*.mkv",
            ),
        )

    def list_original_loop_videos(self):

        extensions = (
            "*.mp4",
            "*.mov",
            "*.webm",
            "*.mkv",
        )

        legacy = self._list_files(
            self.loop_videos_dir,
            extensions,
        )
        original = self._list_files(
            self.loop_videos_original_dir,
            extensions,
        )

        return self._dedupe_paths(
            legacy + original
        )

    def list_images(self):

        return self._list_files(
            self.images_dir,
            (
                "*.jpg",
                "*.jpeg",
                "*.png",
                "*.webp",
            ),
        )

    def list_vod_loop_videos(
        self,
        profile_key=None,
    ):

        extensions = (
            "*.mp4",
            "*.mov",
            "*.webm",
            "*.mkv",
        )

        if not profile_key:
            return self._list_files(
                self.vod_loop_videos_dir,
                extensions,
            )

        ready = self._list_files(
            self.vod_profile_loop_videos_ready_dir(
                profile_key
            ),
            extensions,
        )

        if ready:
            return ready

        original = self._list_files(
            self.vod_profile_loop_videos_original_dir(
                profile_key
            ),
            extensions,
        )
        legacy = self._list_files(
            self.vod_profile_loop_videos_dir(
                profile_key
            ),
            extensions,
        )

        return self._dedupe_paths(
            original + legacy
        )

    def list_vod_original_loop_videos(
        self,
        profile_key,
    ):

        extensions = (
            "*.mp4",
            "*.mov",
            "*.webm",
            "*.mkv",
        )

        original = self._list_files(
            self.vod_profile_loop_videos_original_dir(
                profile_key
            ),
            extensions,
        )
        legacy = self._list_files(
            self.vod_profile_loop_videos_dir(
                profile_key
            ),
            extensions,
        )

        return self._dedupe_paths(
            original + legacy
        )

    def list_vod_ready_loop_videos(
        self,
        profile_key,
    ):

        return self._list_files(
            self.vod_profile_loop_videos_ready_dir(
                profile_key
            ),
            (
                "*.mp4",
                "*.mov",
                "*.webm",
                "*.mkv",
            ),
        )

    def list_vod_thumbnails(
        self,
        profile_key=None,
    ):

        directory = (
            self.vod_profile_thumbnails_dir(
                profile_key
            )
            if profile_key
            else self.vod_thumbnails_dir
        )

        return self._list_files(
            directory,
            (
                "*.jpg",
                "*.jpeg",
                "*.png",
                "*.webp",
            ),
        )

    def list_vod_outputs(self):

        return self._list_files(
            self.vod_output_dir,
            (
                "*.mp4",
                "*.mov",
                "*.mkv",
            ),
        )

    def list_incoming_files(self):

        extensions = (
            "*.mp3",
            "*.wav",
            "*.m4a",
            "*.aac",
            "*.flac",
            "*.mp4",
            "*.mov",
            "*.webm",
            "*.mkv",
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.webp",
        )

        files = []

        for folder in (
            self.incoming_dir,
            self.incoming_music_dir,
            self.incoming_loop_videos_dir,
            self.incoming_images_dir,
        ):
            files.extend(
                self._list_files(
                    folder,
                    extensions,
                )
            )

        return self._dedupe_paths(files)

    def media_metadata_path(
        self,
        media_type,
        source_path,
    ):

        safe_name = (
            Path(source_path)
            .name
            .replace("/", "_")
        )

        return (
            self.metadata_dir
            / media_type
            / f"{safe_name}.json"
        )

    def loop_video_metadata_path(
        self,
        source_path,
    ):

        return self.media_metadata_path(
            "loop_videos",
            source_path,
        )

    def music_metadata_path(
        self,
        source_path,
    ):

        return self.media_metadata_path(
            "music",
            source_path,
        )
