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

    def _utc_now(self):
        return datetime.now(
            timezone.utc
        ).isoformat()

    def _save_state(
        self,
        **updates,
    ):
        state = self.library.get_vod_state()
        state.update(updates)
        self.library.save_vod_state(
            state
        )
        return state

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

    def _validate_render_result(
        self,
        render_result,
    ):
        if not isinstance(
            render_result,
            dict,
        ):
            raise TypeError(
                "Результат рендера VOD "
                "должен быть словарём."
            )

        output_value = str(
            render_result.get(
                "output_path",
                "",
            )
        ).strip()
        manifest_value = render_result.get(
            "manifest"
        )
        manifest_path_value = str(
            render_result.get(
                "manifest_path",
                "",
            )
        ).strip()

        if not output_value:
            raise RuntimeError(
                "В результате рендера отсутствует "
                "output_path."
            )

        if not isinstance(
            manifest_value,
            dict,
        ):
            raise RuntimeError(
                "В результате рендера отсутствует "
                "корректный manifest."
            )

        if not manifest_path_value:
            raise RuntimeError(
                "В результате рендера отсутствует "
                "manifest_path."
            )

        output_path = Path(
            output_value
        )
        manifest_path = Path(
            manifest_path_value
        )

        if not output_path.exists():
            raise FileNotFoundError(
                "Итоговое VOD-видео "
                f"не найдено: {output_path}"
            )

        if not output_path.is_file():
            raise RuntimeError(
                "Путь итогового VOD-видео "
                f"не является файлом: {output_path}"
            )

        if not manifest_path.exists():
            raise FileNotFoundError(
                "Файл манифеста VOD "
                f"не найден: {manifest_path}"
            )

        return (
            output_path,
            manifest_value,
            manifest_path,
        )

    def publish(
        self,
        plan,
        render_result,
    ):
        if not isinstance(
            plan,
            dict,
        ):
            raise TypeError(
                "VOD-план должен быть словарём."
            )

        if not plan.get("ready"):
            raise RuntimeError(
                "VOD-план не готов: "
                f"{plan.get('reason', '')}"
            )

        (
            output_path,
            manifest,
            manifest_path,
        ) = self._validate_render_result(
            render_result
        )

        thumbnail_value = str(
            plan.get(
                "thumbnail",
                "",
            )
        ).strip()

        if not thumbnail_value:
            raise RuntimeError(
                "В VOD-плане отсутствует thumbnail."
            )

        thumbnail_path = Path(
            thumbnail_value
        )

        if not thumbnail_path.exists():
            raise FileNotFoundError(
                "Превью VOD не найдено: "
                f"{thumbnail_path}"
            )

        if not thumbnail_path.is_file():
            raise RuntimeError(
                "Путь превью VOD не является "
                f"файлом: {thumbnail_path}"
            )

        title = str(
            plan.get(
                "title",
                "",
            )
        ).strip()

        if not title:
            raise RuntimeError(
                "В VOD-плане отсутствует title."
            )

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
        ).strip() or "public"
        tags = self._build_tags(
            plan
        )

        self._save_state(
            running=True,
            stage="uploading",
            started_at=self._utc_now(),
            finished_at="",
            output_file=str(
                output_path
            ),
            youtube_video_id="",
            youtube_url="",
            last_error="",
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

            if not isinstance(
                upload_result,
                dict,
            ):
                raise RuntimeError(
                    "YouTube uploader вернул "
                    "некорректный результат."
                )

            video_id = str(
                upload_result.get(
                    "video_id",
                    "",
                )
            ).strip()
            youtube_url = str(
                upload_result.get(
                    "youtube_url",
                    "",
                )
            ).strip()

            if not video_id:
                raise RuntimeError(
                    "YouTube uploader не вернул "
                    "video_id."
                )

            if not youtube_url:
                raise RuntimeError(
                    "YouTube uploader не вернул "
                    "youtube_url."
                )

            published_at = self._utc_now()

            used_paths = (
                self._used_track_paths(
                    manifest
                )
            )

            if used_paths:
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

            self._save_state(
                running=False,
                stage="published",
                finished_at=published_at,
                output_file=(
                    ""
                    if deleted_output
                    else str(
                        output_path
                    )
                ),
                youtube_video_id=video_id,
                youtube_url=youtube_url,
                last_error="",
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
            self._save_state(
                running=False,
                stage="upload_error",
                finished_at=self._utc_now(),
                output_file=str(
                    output_path
                ),
                last_error=str(error),
            )
            raise
