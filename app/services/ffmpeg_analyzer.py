import re
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
FFMPEG_LOG_ROOT = PROJECT_ROOT / "logs" / "ffmpeg"
MAX_ARCHIVE_LOGS_PER_CHANNEL = 20


def safe_channel_name(channel):
    return str(channel).replace("/", "_")


def channel_log_dir(channel):
    path = FFMPEG_LOG_ROOT / safe_channel_name(channel)
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_log_path(channel):
    return channel_log_dir(channel) / "latest.log"


def archive_log_path(channel):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return channel_log_dir(channel) / f"{timestamp}.log"


def cleanup_archive_logs(channel, keep=MAX_ARCHIVE_LOGS_PER_CHANNEL):
    directory = channel_log_dir(channel)
    archives = sorted(
        [path for path in directory.glob("*.log") if path.name != "latest.log"],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_path in archives[max(0, int(keep)):]:
        try:
            old_path.unlink()
        except FileNotFoundError:
            pass


def write_ffmpeg_log(channel, text, archive=True):
    text = str(text or "")

    latest = latest_log_path(channel)
    latest.write_text(text, encoding="utf-8", errors="replace")

    result = {
        "latest": str(latest),
        "archive": "",
    }

    if archive:
        archived = archive_log_path(channel)
        archived.write_text(text, encoding="utf-8", errors="replace")
        result["archive"] = str(archived)
        cleanup_archive_logs(channel)

    return result


def read_latest_ffmpeg_log(channel, limit_chars=12000):
    path = latest_log_path(channel)

    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit_chars:]


def extract_last_lines(text, limit=40):
    lines = str(text or "").splitlines()
    return "\n".join(lines[-limit:])


def extract_paths(text):
    pattern = r"(/opt/youtubefactory/[^'\"\s]+(?:\s[^'\"\n\r]+)*)"
    found = []

    for match in re.findall(pattern, str(text or "")):
        clean = match.strip().strip("'\"")
        if clean and clean not in found:
            found.append(clean)

    return found[:10]


def analyze_ffmpeg_output(returncode, output):
    text = str(output or "")
    lower = text.lower()
    last_lines = extract_last_lines(text, limit=50)
    paths = extract_paths(text)

    result = {
        "returncode": returncode,
        "type": "unknown",
        "title": "FFmpeg завершился с ошибкой",
        "what_happened": "FFmpeg завершился с ненулевым кодом, но причина пока не определена.",
        "recommended_actions": [
            "Откройте последние строки FFmpeg-лога.",
            "Проверьте YouTube Live, сеть, loop-видео и музыкальные файлы.",
            "Если ошибка повторяется, пришлите latest.log.",
        ],
        "recoverable": False,
        "action": "need_user",
        "paths": paths,
        "last_lines": last_lines,
    }

    if "exiting normally, received signal 15" in lower or "immediate exit requested" in lower:
        result.update(
            {
                "type": "manual_stop",
                "title": "Штатная остановка FFmpeg",
                "what_happened": "FFmpeg был остановлен системой вручную через systemctl stop или кнопку остановки.",
                "recommended_actions": [
                    "Ничего исправлять не нужно.",
                    "Если нужно продолжить эфир — запустите канал снова.",
                ],
                "recoverable": True,
                "action": "stop",
            }
        )
        return result

    if "broken pipe" in lower or "error writing trailer: broken pipe" in lower:
        result.update(
            {
                "type": "rtmp_broken_pipe",
                "title": "RTMP-соединение с YouTube разорвано",
                "what_happened": "YouTube или сеть закрыли RTMP-соединение. Медиафайлы при этом могли быть полностью исправны.",
                "recommended_actions": [
                    "Система должна попытаться создать новый эфир автоматически.",
                    "Если автоматическое восстановление не удалось, проверьте YouTube Live и сеть сервера.",
                ],
                "recoverable": True,
                "action": "restart_broadcast",
            }
        )
        return result

    if "connection reset" in lower or "connection timed out" in lower or "timed out" in lower:
        result.update(
            {
                "type": "network_disconnect",
                "title": "Сетевой разрыв во время трансляции",
                "what_happened": "Соединение с YouTube/RTMP временно оборвалось.",
                "recommended_actions": [
                    "Система должна попытаться восстановить эфир автоматически.",
                    "Если восстановление не удалось, проверьте сеть сервера.",
                ],
                "recoverable": True,
                "action": "restart_broadcast",
            }
        )
        return result

    if "no such file or directory" in lower:
        result.update(
            {
                "type": "missing_file",
                "title": "FFmpeg не нашёл файл",
                "what_happened": "Один из файлов, который должен был использовать FFmpeg, отсутствует.",
                "recommended_actions": [
                    "Проверьте пути в деталях ошибки.",
                    "Загрузите недостающий файл заново.",
                    "После исправления восстановите и запустите канал.",
                ],
                "recoverable": False,
            }
        )
        return result

    if "invalid data found" in lower or "error while decoding" in lower or "moov atom not found" in lower:
        result.update(
            {
                "type": "invalid_media",
                "title": "Повреждённый или неподдерживаемый медиафайл",
                "what_happened": "FFmpeg не смог прочитать один из аудио/видео файлов.",
                "recommended_actions": [
                    "Посмотрите путь к файлу в деталях ошибки.",
                    "Удалите подозрительный файл и загрузите его заново.",
                    "Для видео используйте MP4 H.264, 30 FPS, 16:9.",
                    "Для аудио используйте MP3/WAV/M4A без повреждений.",
                ],
                "recoverable": False,
            }
        )
        return result

    if "permission denied" in lower:
        result.update(
            {
                "type": "permission_denied",
                "title": "Нет доступа к файлу",
                "what_happened": "FFmpeg не смог открыть файл из-за прав доступа.",
                "recommended_actions": [
                    "Проверьте права на файлы в library/ и queue/.",
                    "Файлы должны быть доступны пользователю root.",
                    "После исправления восстановите канал.",
                ],
                "recoverable": False,
            }
        )
        return result

    if "server returned 403" in lower or "403 forbidden" in lower:
        result.update(
            {
                "type": "rtmp_forbidden",
                "title": "YouTube отклонил RTMP-поток",
                "what_happened": "YouTube не принял поток. Возможна проблема с ключом трансляции или статусом Live.",
                "recommended_actions": [
                    "Система должна попытаться создать новый эфир автоматически.",
                    "Если ошибка повторяется, переподключите YouTube OAuth.",
                ],
                "recoverable": True,
                "action": "restart_broadcast",
            }
        )
        return result

    return result


def format_ffmpeg_analysis(analysis):
    actions = "\n".join(
        f"{idx}. {item}"
        for idx, item in enumerate(analysis.get("recommended_actions", []), start=1)
    )

    paths = analysis.get("paths") or []
    paths_text = "\n".join(paths) if paths else "—"

    return (
        f"Причина: {analysis.get('title')}\n\n"
        f"Что произошло:\n{analysis.get('what_happened')}\n\n"
        f"Код FFmpeg: {analysis.get('returncode')}\n\n"
        f"Файлы/пути из лога:\n{paths_text}\n\n"
        f"Что сделать:\n{actions}\n\n"
        f"Последние строки FFmpeg:\n{analysis.get('last_lines', '')}"
    )
