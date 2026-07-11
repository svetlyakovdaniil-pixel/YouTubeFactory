import fcntl
import json
import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
BACKUP_ROOT = PROJECT_ROOT / "backups"
LATEST_BACKUP = BACKUP_ROOT / "backup_latest.tar.gz"
PREVIOUS_BACKUP = BACKUP_ROOT / "backup_previous.tar.gz"
OLDER_BACKUP = BACKUP_ROOT / "backup_older.tar.gz"
MANIFEST_PATH = BACKUP_ROOT / "manifest.json"
MAINTENANCE_LOCK = PROJECT_ROOT / "runtime" / "maintenance.lock"

INCLUDE_PATHS = [
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "logs" / "events",
]

CLEAN_PATHS = [
    PROJECT_ROOT / "tmp",
    PROJECT_ROOT / "cache",
]

OUTPUT_MAX_AGE_DAYS = 3
MAX_BACKUPS = 3
RECENT_CYCLE_SECONDS = 300


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {
            "last_backup_at": "",
            "last_content_hash": "",
            "last_cleanup_at": "",
            "last_cycle_cleanup_at": "",
        }

    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_backup_at": "",
            "last_content_hash": "",
            "last_cleanup_at": "",
            "last_cycle_cleanup_at": "",
        }


def save_manifest(data):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_iso(value):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def path_size(path):
    path = Path(path)

    if not path.exists():
        return 0

    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except Exception:
            return 0

    total = 0

    for item in path.rglob("*"):
        if not item.is_file():
            continue

        try:
            total += item.stat().st_size
        except Exception:
            pass

    return total


def safe_remove_path(path):
    path = Path(path)

    if not path.exists():
        return {
            "files": 0,
            "bytes": 0,
        }

    removed_files = 0
    removed_bytes = path_size(path)

    if path.is_file() or path.is_symlink():
        try:
            path.unlink()
            removed_files = 1
        except Exception:
            return {
                "files": 0,
                "bytes": 0,
            }

        return {
            "files": removed_files,
            "bytes": removed_bytes,
        }

    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
                removed_files += 1
            elif child.is_dir():
                child.rmdir()
        except Exception:
            pass

    try:
        path.rmdir()
    except Exception:
        pass

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def active_ffmpeg_processes():
    result = subprocess.run(
        ["pgrep", "-af", "ffmpeg"],
        capture_output=True,
        text=True,
        check=False,
    )

    active = []

    for line in result.stdout.splitlines():
        lower = line.lower()

        if "rtmp://" not in lower and "rtmps://" not in lower:
            continue

        active.append(line.strip())

    return active


def maintenance_allowed():
    return len(active_ffmpeg_processes()) == 0


def file_fingerprint(path):
    try:
        stat = path.stat()
        return f"{path}:{stat.st_size}:{int(stat.st_mtime)}"
    except Exception:
        return f"{path}:missing"


def calculate_content_hash():
    import hashlib

    items = []

    for root in INCLUDE_PATHS:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*")):
            if path.is_file():
                items.append(file_fingerprint(path))

    raw = "\n".join(items).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def rotate_backups():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    if OLDER_BACKUP.exists():
        OLDER_BACKUP.unlink()

    if PREVIOUS_BACKUP.exists():
        PREVIOUS_BACKUP.rename(OLDER_BACKUP)

    if LATEST_BACKUP.exists():
        LATEST_BACKUP.rename(PREVIOUS_BACKUP)


def prune_backup_files():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    backup_files = sorted(
        [
            path
            for path in BACKUP_ROOT.iterdir()
            if path.is_file()
            and path.name != MANIFEST_PATH.name
            and (
                path.suffix in {".gz", ".tgz", ".zip", ".tar"}
                or path.name.endswith(".tar.gz")
            )
        ],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    removed_files = 0
    removed_bytes = 0

    for path in backup_files[MAX_BACKUPS:]:
        try:
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
        except Exception:
            pass

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def create_backup(force=False):
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные FFmpeg-трансляции. Backup отложен.",
        }

    manifest = load_manifest()
    current_hash = calculate_content_hash()

    if (
        not force
        and manifest.get("last_content_hash") == current_hash
        and LATEST_BACKUP.exists()
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "Изменений нет. Новый backup не нужен.",
            "path": str(LATEST_BACKUP),
        }

    rotate_backups()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    with tarfile.open(LATEST_BACKUP, "w:gz") as tar:
        for path in INCLUDE_PATHS:
            if path.exists():
                tar.add(
                    path,
                    arcname=str(path.relative_to(PROJECT_ROOT)),
                )

        systemd_dir = Path("/etc/systemd/system")

        for service in systemd_dir.glob("youtubefactory*.service"):
            tar.add(
                service,
                arcname=f"systemd/{service.name}",
            )

    prune_backup_files()

    manifest["last_backup_at"] = now_iso()
    manifest["last_content_hash"] = current_hash
    save_manifest(manifest)

    return {
        "ok": True,
        "skipped": False,
        "path": str(LATEST_BACKUP),
        "size": (
            LATEST_BACKUP.stat().st_size
            if LATEST_BACKUP.exists()
            else 0
        ),
    }


def cleanup_queue():
    queue_root = PROJECT_ROOT / "queue"

    if not queue_root.exists():
        return {
            "files": 0,
            "bytes": 0,
        }

    removed_files = 0
    removed_bytes = 0

    for channel_dir in queue_root.iterdir():
        if not channel_dir.is_dir():
            continue

        for item in channel_dir.iterdir():
            if item.name == "active.mp4":
                continue

            result = safe_remove_path(item)
            removed_files += result["files"]
            removed_bytes += result["bytes"]

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def cleanup_ffmpeg_logs():
    log_root = PROJECT_ROOT / "logs" / "ffmpeg"

    if not log_root.exists():
        return {
            "files": 0,
            "bytes": 0,
        }

    removed_files = 0
    removed_bytes = 0

    for path in log_root.rglob("*"):
        if not path.is_file():
            continue

        if path.name == "latest.log":
            continue

        try:
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
        except Exception:
            pass

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def cleanup_old_output(max_age_days=OUTPUT_MAX_AGE_DAYS):
    output_root = PROJECT_ROOT / "output"

    if not output_root.exists():
        return {
            "files": 0,
            "bytes": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed_files = 0
    removed_bytes = 0

    for path in output_root.rglob("*"):
        if not path.is_file():
            continue

        try:
            modified = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=timezone.utc,
            )
        except Exception:
            continue

        if modified >= cutoff:
            continue

        try:
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
        except Exception:
            pass

    for directory in sorted(output_root.rglob("*"), reverse=True):
        if not directory.is_dir():
            continue

        try:
            directory.rmdir()
        except Exception:
            pass

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def cleanup_temp():
    removed_files = 0
    removed_bytes = 0

    for path in CLEAN_PATHS:
        result = safe_remove_path(path)
        removed_files += result["files"]
        removed_bytes += result["bytes"]

    queue_result = cleanup_queue()
    removed_files += queue_result["files"]
    removed_bytes += queue_result["bytes"]

    (PROJECT_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "cache").mkdir(parents=True, exist_ok=True)

    return {
        "files": removed_files,
        "bytes": removed_bytes,
    }


def disk_usage():
    usage = shutil.disk_usage(PROJECT_ROOT)

    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
    }


def run_cleanup():
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные FFmpeg-трансляции. Очистка отложена.",
            "removed": 0,
            "removed_bytes": 0,
        }

    before = disk_usage()

    categories = {
        "temporary": cleanup_temp(),
        "ffmpeg_logs": cleanup_ffmpeg_logs(),
        "output": cleanup_old_output(),
        "backups": prune_backup_files(),
    }

    removed_files = sum(
        item.get("files", 0)
        for item in categories.values()
    )
    removed_bytes = sum(
        item.get("bytes", 0)
        for item in categories.values()
    )

    after = disk_usage()

    manifest = load_manifest()
    manifest["last_cleanup_at"] = now_iso()
    save_manifest(manifest)

    return {
        "ok": True,
        "skipped": False,
        "removed": removed_files,
        "removed_bytes": removed_bytes,
        "categories": categories,
        "disk_before": before,
        "disk_after": after,
    }


def run_cycle_maintenance():
    MAINTENANCE_LOCK.parent.mkdir(parents=True, exist_ok=True)

    with open(MAINTENANCE_LOCK, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        manifest = load_manifest()
        last_cycle = parse_iso(
            manifest.get("last_cycle_cleanup_at", "")
        )

        if last_cycle is not None:
            age = (
                datetime.now(timezone.utc) - last_cycle
            ).total_seconds()

            if age < RECENT_CYCLE_SECONDS:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "Очистка этого цикла уже выполнена другим каналом.",
                }

        cleanup = run_cleanup()

        if cleanup.get("ok") and not cleanup.get("skipped"):
            manifest = load_manifest()
            manifest["last_cycle_cleanup_at"] = now_iso()
            save_manifest(manifest)

        return cleanup


def run_maintenance(force_backup=False):
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные FFmpeg-трансляции. Обслуживание отложено.",
            "backup": None,
            "cleanup": None,
        }

    cleanup = run_cleanup()
    backup = create_backup(force=force_backup)

    return {
        "ok": True,
        "skipped": False,
        "cleanup": cleanup,
        "backup": backup,
    }


def list_backups():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    backups = []

    for path in sorted(
        BACKUP_ROOT.glob("*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        if not path.is_file() or path.name == MANIFEST_PATH.name:
            continue

        backups.append(
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "modified": datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
            }
        )

    return backups[:MAX_BACKUPS]


def format_bytes(value):
    value = float(value or 0)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"

        value /= 1024

    return f"{value:.2f} TB"


def format_cleanup_report(result):
    if result.get("skipped"):
        return f"🧹 Очистка пропущена\n\n{result.get('reason', '')}"

    categories = result.get("categories") or {}
    disk_after = result.get("disk_after") or {}

    lines = [
        "🧹 Очистка завершена",
        "",
        f"Временные файлы: {format_bytes(categories.get('temporary', {}).get('bytes', 0))}",
        f"FFmpeg-логи: {format_bytes(categories.get('ffmpeg_logs', {}).get('bytes', 0))}",
        f"Старые output-файлы: {format_bytes(categories.get('output', {}).get('bytes', 0))}",
        f"Старые backup-файлы: {format_bytes(categories.get('backups', {}).get('bytes', 0))}",
        "",
        f"Всего освобождено: {format_bytes(result.get('removed_bytes', 0))}",
        f"Свободно на диске: {format_bytes(disk_after.get('free', 0))}",
    ]

    return "\n".join(lines)


def format_maintenance_report(result):
    if result.get("skipped"):
        return (
            "🛠 Обслуживание отложено\n\n"
            f"{result.get('reason', '')}"
        )

    lines = [
        "🛠 Обслуживание завершено",
        "",
    ]

    cleanup = result.get("cleanup") or {}
    backup = result.get("backup") or {}

    if cleanup:
        if cleanup.get("skipped"):
            lines.append(
                f"🧹 Очистка: {cleanup.get('reason')}"
            )
        else:
            lines.append(
                "✅ Очистка: "
                f"{format_bytes(cleanup.get('removed_bytes', 0))}"
            )

    if backup:
        if backup.get("skipped"):
            lines.append(
                f"📦 Backup: {backup.get('reason')}"
            )
        else:
            lines.append(
                f"✅ Backup: {backup.get('path')}"
            )

    return "\n".join(lines)
