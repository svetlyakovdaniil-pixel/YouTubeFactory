from pathlib import Path

from googleapiclient.http import MediaFileUpload

from app.youtube.api_retry import safe_execute
from app.youtube.auth import get_youtube_service


VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}

THUMBNAIL_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class YouTubeUploader:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.youtube = get_youtube_service(
            channel_name
        )

    def _validate_video(self, video_path):
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(
                f"Видео не найдено: {video_path}"
            )

        if not video_path.is_file():
            raise ValueError(
                f"Это не файл: {video_path}"
            )

        suffix = video_path.suffix.lower()

        if suffix not in VIDEO_MIME_TYPES:
            raise ValueError(
                "Неподдерживаемый формат видео: "
                f"{suffix or 'без расширения'}"
            )

        if video_path.stat().st_size <= 0:
            raise ValueError(
                f"Видео пустое: {video_path}"
            )

        return video_path

    def _validate_thumbnail(
        self,
        thumbnail_path,
    ):
        if not thumbnail_path:
            return None

        thumbnail_path = Path(
            thumbnail_path
        )

        if not thumbnail_path.exists():
            raise FileNotFoundError(
                "Превью не найдено: "
                f"{thumbnail_path}"
            )

        if not thumbnail_path.is_file():
            raise ValueError(
                f"Это не файл: {thumbnail_path}"
            )

        suffix = thumbnail_path.suffix.lower()

        if suffix not in THUMBNAIL_MIME_TYPES:
            raise ValueError(
                "Неподдерживаемый формат превью: "
                f"{suffix or 'без расширения'}"
            )

        return thumbnail_path

    def upload_video(
        self,
        video_path,
        title,
        description,
        privacy="public",
        tags=None,
        category_id="10",
        made_for_kids=False,
    ):
        video_path = self._validate_video(
            video_path
        )

        title = str(title or "").strip()
        description = str(
            description or ""
        ).strip()
        privacy = str(
            privacy or "public"
        ).strip().lower()

        if not title:
            raise ValueError(
                "Название видео не может "
                "быть пустым."
            )

        if len(title) > 100:
            raise ValueError(
                "Название YouTube не может "
                "быть длиннее 100 символов."
            )

        if privacy not in {
            "public",
            "unlisted",
            "private",
        }:
            raise ValueError(
                "privacy должен быть public, "
                "unlisted или private."
            )

        clean_tags = []

        for tag in tags or []:
            tag = str(tag or "").strip()

            if (
                tag
                and tag not in clean_tags
            ):
                clean_tags.append(tag)

        media = MediaFileUpload(
            str(video_path),
            mimetype=VIDEO_MIME_TYPES[
                video_path.suffix.lower()
            ],
            chunksize=8 * 1024 * 1024,
            resumable=True,
        )

        request = self.youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": str(
                        category_id
                    ),
                    "tags": clean_tags,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": bool(
                        made_for_kids
                    ),
                },
            },
            media_body=media,
            notifySubscribers=False,
        )

        response = safe_execute(
            request,
            operation_name=(
                "Загрузка VOD-видео на YouTube"
            ),
        )

        video_id = response.get("id", "")

        if not video_id:
            raise RuntimeError(
                "YouTube не вернул video_id "
                "после загрузки."
            )

        return {
            "video_id": video_id,
            "youtube_url": (
                "https://www.youtube.com/watch"
                f"?v={video_id}"
            ),
            "response": response,
        }

    def set_thumbnail(
        self,
        video_id,
        thumbnail_path,
    ):
        video_id = str(
            video_id or ""
        ).strip()

        if not video_id:
            raise ValueError(
                "video_id не может быть пустым."
            )

        thumbnail_path = (
            self._validate_thumbnail(
                thumbnail_path
            )
        )

        if thumbnail_path is None:
            return {
                "skipped": True,
                "reason": "thumbnail_not_provided",
            }

        media = MediaFileUpload(
            str(thumbnail_path),
            mimetype=THUMBNAIL_MIME_TYPES[
                thumbnail_path.suffix.lower()
            ],
            resumable=False,
        )

        request = self.youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        )

        response = safe_execute(
            request,
            operation_name=(
                "Установка превью VOD-видео"
            ),
        )

        return {
            "skipped": False,
            "response": response,
        }

    def upload_vod(
        self,
        video_path,
        thumbnail_path,
        title,
        description,
        privacy="public",
        tags=None,
        category_id="10",
    ):
        upload_result = self.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            privacy=privacy,
            tags=tags,
            category_id=category_id,
            made_for_kids=False,
        )

        thumbnail_result = self.set_thumbnail(
            video_id=upload_result[
                "video_id"
            ],
            thumbnail_path=thumbnail_path,
        )

        return {
            **upload_result,
            "thumbnail_result": (
                thumbnail_result
            ),
        }
