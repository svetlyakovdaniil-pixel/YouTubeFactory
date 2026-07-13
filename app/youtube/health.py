from pathlib import Path

from app.youtube.auth import get_youtube_service
from app.youtube.api_retry import safe_execute


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"


def check_youtube_connection(channel_name):
    youtube_dir = LIBRARY_ROOT / channel_name / "youtube"
    client_secret = youtube_dir / "client_secret.json"
    token = youtube_dir / "token.json"

    result = {
        "ok": False,
        "client_secret_exists": client_secret.exists(),
        "token_exists": token.exists(),
        "channel_id": "",
        "channel_title": "",
        "error": "",
    }

    if not client_secret.exists():
        result["error"] = "Не найден client_secret.json"
        return result

    if not token.exists():
        result["error"] = "Не найден token.json"
        return result

    try:
        youtube = get_youtube_service(channel_name)

        request = youtube.channels().list(
            part="id,snippet",
            mine=True,
        )

        response = safe_execute(
            request,
            operation_name="Проверка подключения YouTube-канала",
        )

        items = response.get("items", [])

        if not items:
            result["error"] = (
                "Токен работает, но YouTube-канал не найден"
            )
            return result

        item = items[0]

        result.update({
            "ok": True,
            "channel_id": item.get("id", ""),
            "channel_title": (
                item.get("snippet", {}).get("title", "")
            ),
        })

        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result
