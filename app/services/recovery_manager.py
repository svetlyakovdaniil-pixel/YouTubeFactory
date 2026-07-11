from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.services.channel_status import build_channel_status
from app.services.error_advisor import analyze_error


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"


def has_valid_thumbnail(channel):
    library = ChannelLibrary(channel)

    for image in library.list_images():
        suffix = image.suffix.lower()

        if suffix not in [".jpg", ".jpeg", ".png"]:
            continue

        try:
            if image.stat().st_size <= 2 * 1024 * 1024:
                return True
        except Exception:
            continue

    return False


def recovery_checks(channel):
    status = build_channel_status(
        channel,
        systemd_active=False,
    )

    state = status["state"]
    last_error = state.get("last_error", "")
    advice = analyze_error(last_error)

    checks = []

    checks.append(
        {
            "key": "music",
            "label": "Музыка",
            "ok": status["music_ready"],
            "message": "Музыка найдена" if status["music_ready"] else "Музыка отсутствует",
        }
    )

    checks.append(
        {
            "key": "video",
            "label": "Loop-видео",
            "ok": status["video_ready"],
            "message": "Видео найдено" if status["video_ready"] else "Loop-видео отсутствует",
        }
    )

    checks.append(
        {
            "key": "youtube",
            "label": "YouTube",
            "ok": status["youtube_ready"],
            "message": "YouTube подключен" if status["youtube_ready"] else "YouTube не подключен",
        }
    )

    checks.append(
        {
            "key": "systemd",
            "label": "Systemd",
            "ok": status["service_ok"],
            "message": "Systemd-сервис найден" if status["service_ok"] else "Systemd-сервис отсутствует",
        }
    )

    if advice["title"] == "Превью слишком большое":
        thumb_ok = has_valid_thumbnail(channel)

        checks.append(
            {
                "key": "thumbnail",
                "label": "Превью",
                "ok": thumb_ok,
                "message": "Подходящее превью найдено" if thumb_ok else "Нет JPG/PNG превью меньше 2 МБ",
            }
        )

    if advice["title"] == "Превышен лимит YouTube API":
        checks.append(
            {
                "key": "rate_limit",
                "label": "YouTube API лимит",
                "ok": False,
                "message": "Нужно подождать 15–60 минут и не запускать канал повторно много раз",
            }
        )

    failed = [item for item in checks if not item["ok"]]

    return {
        "ok": len(failed) == 0,
        "channel": channel,
        "error_title": advice["title"],
        "what_happened": advice["what_happened"],
        "recommended_actions": advice["recommended_actions"],
        "checks": checks,
        "failed": failed,
    }


def format_recovery_report(channel):
    result = recovery_checks(channel)

    lines = [
        f"🔧 Восстановление канала: {channel}",
        "",
        f"Причина аварии: {result['error_title']}",
        "",
        "Проверки:",
    ]

    for item in result["checks"]:
        icon = "✅" if item["ok"] else "❌"
        lines.append(f"{icon} {item['label']}: {item['message']}")

    if result["ok"]:
        lines.extend(
            [
                "",
                "🟢 Причина устранена. Аварию можно снять.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "🔴 Аварию пока нельзя снять.",
                "",
                "Что сделать:",
            ]
        )

        for idx, action in enumerate(result["recommended_actions"], start=1):
            lines.append(f"{idx}. {action}")

    return "\n".join(lines), result


def recover_channel(channel):
    report, result = format_recovery_report(channel)

    if not result["ok"]:
        return {
            "ok": False,
            "message": report,
            "result": result,
        }

    library = ChannelLibrary(channel)
    state = library.get_state()

    state["paused"] = False
    state["last_error"] = ""
    state["running"] = False
    state["watch_url"] = ""
    state["started_at"] = ""
    state["current_track"] = ""
    state["track_index"] = 0

    library.save_state(state)

    return {
        "ok": True,
        "message": report + "\n\n✅ Авария снята. Канал можно запускать.",
        "result": result,
    }
