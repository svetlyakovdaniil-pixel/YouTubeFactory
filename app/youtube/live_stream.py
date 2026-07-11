from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from app.youtube.auth import get_youtube_service


REUSABLE_BROADCAST_STATUSES = {
    "created",
    "ready",
    "testing",
    "testStarting",
    "liveStarting",
    "live",
}

UPCOMING_BROADCAST_STATUSES = {
    "created",
    "ready",
    "testing",
    "testStarting",
    "liveStarting",
}


class YouTubeLiveStream:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.youtube = get_youtube_service(channel_name)

    def create_broadcast(self, title, description=""):
        start_time = (
            datetime.now(timezone.utc) + timedelta(minutes=2)
        ).isoformat()

        request = self.youtube.liveBroadcasts().insert(
            part="snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "scheduledStartTime": start_time,
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "enableAutoStart": True,
                    "enableAutoStop": True,
                    "enableDvr": True,
                    "recordFromStart": True,
                },
            },
        )
        return request.execute()

    def create_stream(self, title):
        request = self.youtube.liveStreams().insert(
            part="snippet,cdn",
            body={
                "snippet": {"title": title},
                "cdn": {
                    "ingestionType": "rtmp",
                    "resolution": "1440p",
                    "frameRate": "60fps",
                },
            },
        )
        return request.execute()

    def bind(self, broadcast_id, stream_id):
        return self.youtube.liveBroadcasts().bind(
            part="id,contentDetails",
            id=broadcast_id,
            streamId=stream_id,
        ).execute()

    def get_broadcast(self, broadcast_id):
        response = self.youtube.liveBroadcasts().list(
            part="id,snippet,status,contentDetails",
            id=broadcast_id,
            maxResults=1,
        ).execute()
        items = response.get("items", [])
        return items[0] if items else None

    def get_lifecycle_status(self, broadcast_id):
        broadcast = self.get_broadcast(broadcast_id)
        if not broadcast:
            return "missing"
        return broadcast.get("status", {}).get("lifeCycleStatus", "")

    def is_event_reusable(self, broadcast_id):
        return self.get_lifecycle_status(broadcast_id) in REUSABLE_BROADCAST_STATUSES

    def delete_if_upcoming(self, broadcast_id):
        status = self.get_lifecycle_status(broadcast_id)

        if status == "missing":
            return {"ok": True, "deleted": False, "status": status}

        if status not in UPCOMING_BROADCAST_STATUSES:
            return {"ok": True, "deleted": False, "status": status}

        self.youtube.liveBroadcasts().delete(id=broadcast_id).execute()
        return {"ok": True, "deleted": True, "status": status}

    def set_thumbnail(self, broadcast_id, thumbnail_path):
        if not thumbnail_path:
            return None

        thumbnail_path = Path(thumbnail_path)
        if not thumbnail_path.exists():
            return None

        suffix = thumbnail_path.suffix.lower()
        if suffix not in [".jpg", ".jpeg", ".png"]:
            return {
                "skipped": True,
                "reason": "Unsupported thumbnail format",
                "path": str(thumbnail_path),
            }

        mime_type = "image/png" if suffix == ".png" else "image/jpeg"
        media = MediaFileUpload(
            str(thumbnail_path),
            mimetype=mime_type,
            resumable=False,
        )

        return self.youtube.thumbnails().set(
            videoId=broadcast_id,
            media_body=media,
        ).execute()

    def create_live_event(self, title, description="", thumbnail_path=None):
        broadcast = self.create_broadcast(title=title, description=description)
        stream = self.create_stream(title=title)
        self.bind(broadcast_id=broadcast["id"], stream_id=stream["id"])

        thumbnail_result = None
        if thumbnail_path:
            thumbnail_result = self.set_thumbnail(
                broadcast_id=broadcast["id"],
                thumbnail_path=thumbnail_path,
            )

        ingestion = stream["cdn"]["ingestionInfo"]
        return {
            "broadcast_id": broadcast["id"],
            "stream_id": stream["id"],
            "watch_url": f"https://www.youtube.com/watch?v={broadcast['id']}",
            "rtmp_url": ingestion["ingestionAddress"],
            "stream_key": ingestion["streamName"],
            "thumbnail_path": str(thumbnail_path) if thumbnail_path else "",
            "thumbnail_result": thumbnail_result,
        }
