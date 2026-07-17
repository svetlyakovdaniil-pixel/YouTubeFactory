import random
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.channel_library import (
    ChannelLibrary,
    WEEK_DAYS,
)
from app.services.track_library import TrackLibrary


class VODPlanner:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(
            channel_name
        )
        self.tracks = TrackLibrary(
            channel_name
        )

    def _current_day(self, config):
        timezone_name = config.get(
            "timezone",
            "Asia/Almaty",
        )
        now = datetime.now(
            ZoneInfo(timezone_name)
        )
        return WEEK_DAYS[now.weekday()], now

    def get_today_plan(self):
        config = self.library.get_vod_config()

        if not config.get("enabled"):
            return {
                "ready": False,
                "reason": "vod_disabled",
                "channel": self.channel_name,
            }

        day, now = self._current_day(config)
        schedule = config.get(
            "weekly_schedule",
            {},
        )
        item = schedule.get(day, {})

        if not item.get("enabled"):
            return {
                "ready": False,
                "reason": "day_disabled",
                "channel": self.channel_name,
                "day": day,
            }

        genre = item.get(
            "genre",
            "",
        ).strip()
        subgenre = item.get(
            "subgenre",
            "",
        ).strip()
        profile_key = item.get(
            "profile_key",
            "",
        ).strip()

        base_result = {
            "ready": False,
            "channel": self.channel_name,
            "day": day,
            "local_date": now.date().isoformat(),
            "genre": genre,
            "subgenre": subgenre,
            "profile_key": profile_key,
        }

        if not genre or not subgenre or not profile_key:
            return {
                **base_result,
                "reason": "schedule_incomplete",
            }

        candidates = (
            self.tracks.select_vod_candidates(
                genre=genre,
                subgenre=subgenre,
            )
        )

        candidate_tracks = [
            {
                "path": str(
                    candidate["audio_path"]
                ),
                "title": (
                    candidate["metadata"].get(
                        "title"
                    )
                    or candidate[
                        "audio_path"
                    ].stem
                ),
                "mood": candidate[
                    "metadata"
                ].get(
                    "mood",
                    "",
                ),
                "bpm": candidate[
                    "metadata"
                ].get("bpm"),
                "vod_uses": int(
                    candidate["metadata"].get(
                        "vod_uses",
                        0,
                    )
                    or 0
                ),
            }
            for candidate in candidates
        ]

        if not candidates:
            return {
                **base_result,
                "reason": "no_matching_tracks",
                "tracks": [],
                "track_count": 0,
            }

        loop_videos = (
            self.library.list_vod_loop_videos(
                profile_key
            )
        )
        thumbnails = (
            self.library.list_vod_thumbnails(
                profile_key
            )
        )

        if not loop_videos:
            return {
                **base_result,
                "reason": "no_loop_video",
                "tracks": candidate_tracks,
                "track_count": len(
                    candidate_tracks
                ),
                "loop_video_count": 0,
                "thumbnail_count": len(
                    thumbnails
                ),
            }

        if not thumbnails:
            return {
                **base_result,
                "reason": "no_thumbnail",
                "tracks": candidate_tracks,
                "track_count": len(
                    candidate_tracks
                ),
                "loop_video_count": len(
                    loop_videos
                ),
                "thumbnail_count": 0,
            }

        minimum = int(
            item.get(
                "min_duration_minutes",
                60,
            )
        )
        maximum = int(
            item.get(
                "max_duration_minutes",
                120,
            )
        )

        titles = [
            value.strip()
            for value in item.get(
                "title_templates",
                [],
            )
            if value.strip()
        ]

        if not titles:
            return {
                **base_result,
                "reason": "no_title_templates",
                "tracks": candidate_tracks,
                "track_count": len(
                    candidate_tracks
                ),
                "loop_video_count": len(
                    loop_videos
                ),
                "thumbnail_count": len(
                    thumbnails
                ),
            }

        description = item.get(
            "description_template",
            "",
        ).strip()

        if not description:
            return {
                **base_result,
                "reason": "no_description",
                "tracks": candidate_tracks,
                "track_count": len(
                    candidate_tracks
                ),
                "loop_video_count": len(
                    loop_videos
                ),
                "thumbnail_count": len(
                    thumbnails
                ),
            }

        return {
            **base_result,
            "ready": True,
            "reason": "",
            "duration_minutes": random.randint(
                minimum,
                maximum,
            ),
            "title": random.choice(titles),
            "description_template": description,
            "loop_video": str(
                random.choice(loop_videos)
            ),
            "thumbnail": str(
                random.choice(thumbnails)
            ),
            "privacy": config.get(
                "privacy",
                "public",
            ),
            "crossfade_seconds": int(
                config.get(
                    "crossfade_seconds",
                    5,
                )
            ),
            "show_track_titles": bool(
                config.get(
                    "show_track_titles",
                    True,
                )
            ),
            "delete_output_after_upload": bool(
                config.get(
                    "delete_output_after_upload",
                    True,
                )
            ),
            "tracks": candidate_tracks,
            "track_count": len(
                candidate_tracks
            ),
            "loop_video_count": len(
                loop_videos
            ),
            "thumbnail_count": len(
                thumbnails
            ),
        }
