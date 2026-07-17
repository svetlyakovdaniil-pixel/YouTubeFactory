from datetime import datetime, timezone
from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.services.track_library import TrackLibrary
from app.youtube.uploader import YouTubeUploader


class VODPublisher:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(
            channel_name
        )
        self.tracks = TrackLibrary(
            channel_name
        )
        self.uploader = YouTubeUploader(
            channel_name
        )

    def _build_tracklist(self, manifest):
        lines = []

        for item in manifest.get(
            "tracks",
            [],
        ):
            timestamp = str(
                item.get(
                    "timestamp",
                    "",
                )
            ).strip()
            title = str(
                item.get(
                    "title",
                    "",
                )
            ).strip()

            if not timestamp or not title:
                continue

            lines.append(
                f"{timestamp} {title}"
            )

        return "\n".join(lines)

    def _build_description(
        self,
        description_template,
        manifest,
    ):
        template = str(
            description_template or ""
        ).strip()
        tracklist = self._build_tracklist(
            manifest
        )

        if "{tracklist}" in template:
            return template.replace(
                "{tracklist}",
                tracklist,
            ).strip()

        if tracklist:
            return (
                f"{template}\n\n{tracklist}"
            ).strip()

        return template

    def _build_tags(self, plan):
        values = [
            self.channel_name,
            plan.get("genre", ""),
            plan.get("subgenre", ""),
            "instrumental",
            "beats",
            "music mix",
        ]

        result = []

        for value in values:
            value = str(
                value or ""
            ).strip()

            if (
                value
                and value not in result
            ):
                result.append(value)

        return result

    def _used_track_paths(self, manifest):
        result = []
        seen = set()

        for item in manifest.get(
            "tracks",
            [],
        ):
            value = str(
                item.get(
                    "source_file",
                    "",
                )
            ).strip()

            if not value:
                continue

            path = Path(value)
            key = str(path)

            if key in seen:
                continue

            seen.add(key)
            result.append(path)

        return result

    def publish(
        self,
        plan,
        render_result,
    ):
        if not plan.get("ready"):
            raise RuntimeError(
                "VOD-план не готов: "
                f"{plan.get('reason', '')}"
            )

        output_path = Path(
            render_result["output_path"]
        )
        manifest = render_result[
            "manifest"
        ]
        manifest_path = Path(
            render_result[
                "manifest_path"
            ]
        )

        if not output_path.exists():
            raise FileNotFoundError(
                "Итоговое VOD-видео "
                f"не найдено: {output_path}"
            )

        thumbnail_path = Path(
            plan["thumbnail"]
        )
        title = str(
            plan.get(
                "title",
                "",
            )
        ).strip()
        description = (
            self._build_description(
                plan.get(
                    "description_template",
                    "",
                ),
                manifest,
            )
        )
        privacy = str(
            plan.get(
                "privacy",
                "public",
            )
        ).strip()
        tags = self._build_tags(
            plan
        )

        state = self.library.get_vod_state()
        state.update(
            {
                "running": True,
                "stage": "uploading",
                "last_error": "",
            }
        )
        self.library.save_vod_state(
            state
        )

        try:
            upload_result = (
                self.uploader.upload_vod(
                    video_path=output_path,
                    thumbnail_path=(
                        thumbnail_path
                    ),
                    title=title,
                    description=description,
                    privacy=privacy,
                    tags=tags,
                    category_id="10",
                )
            )

            video_id = upload_result[
                "video_id"
            ]
            youtube_url = upload_result[
                "youtube_url"
            ]
            published_at = datetime.now(
                timezone.utc
            ).isoformat()

            used_paths = (
                self._used_track_paths(
                    manifest
                )
            )
            self.tracks.mark_vod_used(
                audio_paths=used_paths,
                publication_id=video_id,
            )

            history_item = {
                "channel": self.channel_name,
                "published_at": published_at,
                "local_date": plan.get(
                    "local_date",
                    "",
                ),
                "day": plan.get(
                    "day",
                    "",
                ),
                "genre": plan.get(
                    "genre",
                    "",
                ),
                "subgenre": plan.get(
                    "subgenre",
                    "",
                ),
                "profile_key": plan.get(
                    "profile_key",
                    "",
                ),
                "title": title,
                "description": description,
                "privacy": privacy,
                "youtube_video_id": video_id,
                "youtube_url": youtube_url,
                "thumbnail": str(
                    thumbnail_path
                ),
                "manifest_file": str(
                    manifest_path
                ),
                "output_file": str(
                    output_path
                ),
                "duration_seconds": (
                    manifest.get(
                        "duration_seconds",
                        0,
                    )
                ),
                "tracks": (
                    manifest.get(
                        "tracks",
                        [],
                    )
                ),
            }
            self.library.append_vod_history(
                history_item
            )

            deleted_output = False

            if bool(
                plan.get(
                    "delete_output_after_upload",
                    True,
                )
            ):
                output_path.unlink(
                    missing_ok=True
                )
                deleted_output = True

            state.update(
                {
                    "running": False,
                    "stage": "published",
                    "finished_at": (
                        published_at
                    ),
                    "output_file": (
                        ""
                        if deleted_output
                        else str(
                            output_path
                        )
                    ),
                    "youtube_video_id": (
                        video_id
                    ),
                    "youtube_url": (
                        youtube_url
                    ),
                    "last_error": "",
                }
            )
            self.library.save_vod_state(
                state
            )

            return {
                "video_id": video_id,
                "youtube_url": youtube_url,
                "title": title,
                "description": description,
                "tracklist": (
                    self._build_tracklist(
                        manifest
                    )
                ),
                "history_item": (
                    history_item
                ),
                "deleted_output": (
                    deleted_output
                ),
                "upload_result": (
                    upload_result
                ),
            }

        except Exception as error:
            state.update(
                {
                    "running": False,
                    "stage": "upload_error",
                    "finished_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "last_error": str(error),
                }
            )
            self.library.save_vod_state(
                state
            )
            raise
