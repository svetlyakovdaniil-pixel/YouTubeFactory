import shutil
import subprocess
from pathlib import Path

from app.services.channel_status import build_channel_status
from app.services.telegram_notifier import TelegramNotifier


PROJECT_ROOT = Path("/opt/youtubefactory")
MIN_FREE_GB = 5


def command_exists(command):
    return shutil.which(command) is not None


def disk_free_gb(path=PROJECT_ROOT):
    usage = shutil.disk_usage(path)
    return round(usage.free / (1024 ** 3), 2)


def check_preflight(channel):
    status = build_channel_status(
        channel,
        systemd_active=False,
    )

    checks = []

    checks.append(
        {
            "key": "music",
            "label": "Музыка",
            "ok": status["music_ready"],
            "message": f"{len(status['music_files'])} файлов" if status["music_ready"] else "музыка не загружена",
            "critical": True,
        }
    )

    checks.append(
        {
            "key": "video",
            "label": "Loop-видео",
            "ok": status["video_ready"],
            "message": f"{len(status['loop_videos'])} файлов" if status["video_ready"] else "loop-видео не загружено",
            "critical": True,
        }
    )

    checks.append(
        {
            "key": "youtube",
            "label": "YouTube",
            "ok": status["youtube_ready"],
            "message": "подключен" if status["youtube_ready"] else "YouTube не подключен",
            "critical": True,
        }
    )

    checks.append(
        {
            "key": "systemd",
            "label": "Systemd",
            "ok": status["service_ok"],
            "message": "сервис найден" if status["service_ok"] else "systemd-сервис отсутствует",
            "critical": True,
        }
    )

    ffmpeg_ok = command_exists("ffmpeg")
    checks.append(
        {
            "key": "ffmpeg",
            "label": "FFmpeg",
            "ok": ffmpeg_ok,
            "message": "установлен" if ffmpeg_ok else "ffmpeg не найден",
            "critical": True,
        }
    )

    free_gb = disk_free_gb()
    disk_ok = free_gb >= MIN_FREE_GB
    checks.append(
        {
            "key": "disk",
            "label": "Диск",
            "ok": disk_ok,
            "message": f"свободно {free_gb} GB",
            "critical": True,
        }
    )

    telegram = TelegramNotifier()
    telegram_ok = telegram.is_configured()
    checks.append(
        {
            "key": "telegram",
            "label": "Telegram",
            "ok": telegram_ok,
            "message": "подключен" if telegram_ok else "не подключен",
            "critical": False,
        }
    )

    preview_ok = len(status["image_files"]) > 0
    checks.append(
        {
            "key": "preview",
            "label": "Превью",
            "ok": preview_ok,
            "message": f"{len(status['image_files'])} изображений" if preview_ok else "превью не загружено, эфир запустится без него",
            "critical": False,
        }
    )

    critical_failed = [
        item
        for item in checks
        if item["critical"] and not item["ok"]
    ]

    warnings = [
        item
        for item in checks
        if not item["critical"] and not item["ok"]
    ]

    return {
        "ok": len(critical_failed) == 0,
        "channel": channel,
        "checks": checks,
        "critical_failed": critical_failed,
        "warnings": warnings,
    }


def format_preflight_report(channel):
    result = check_preflight(channel)

    lines = [
        f"🛡 Preflight Check: {channel}",
        "",
        "Проверки:",
    ]

    for item in result["checks"]:
        icon = "✅" if item["ok"] else ("❌" if item["critical"] else "⚠️")
        lines.append(f"{icon} {item['label']}: {item['message']}")

    if result["ok"]:
        lines.extend(
            [
                "",
                "🟢 Канал готов к запуску.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "🔴 Запуск запрещён.",
                "",
                "Что исправить:",
            ]
        )

        for item in result["critical_failed"]:
            lines.append(f"• {item['label']}: {item['message']}")

    return "\n".join(lines), result


def assert_preflight_ok(channel):
    report, result = format_preflight_report(channel)

    if not result["ok"]:
        raise RuntimeError(report)

    return result
