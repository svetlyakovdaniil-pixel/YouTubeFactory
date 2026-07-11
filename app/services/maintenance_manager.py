import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
BACKUP_ROOT = PROJECT_ROOT / "backups"
LATEST_BACKUP = BACKUP_ROOT / "backup_latest.tar.gz"
PREVIOUS_BACKUP = BACKUP_ROOT / "backup_previous.tar.gz"
MANIFEST_PATH = BACKUP_ROOT / "manifest.json"

INCLUDE_PATHS = [
    PROJECT_ROOT / "library",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "logs" / "events",
]

CLEAN_PATHS = [
    PROJECT_ROOT / "tmp",
    PROJECT_ROOT / "cache",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def channel_running_flags():
    runtime_dir = PROJECT_ROOT / "runtime"

    if not runtime_dir.exists():
        return []

    return sorted(runtime_dir.glob("*.running"))


def maintenance_allowed():
    return len(channel_running_flags()) == 0


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {
            "last_backup_at": "",
            "last_content_hash": "",
            "last_cleanup_at": "",
        }

    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_backup_at": "",
            "last_content_hash": "",
            "last_cleanup_at": "",
        }


def save_manifest(data):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
                # Do not include huge media content itself in the hash deeply.
                # Size + mtime is enough to detect practical changes quickly.
                items.append(file_fingerprint(path))

    raw = "\n".join(items).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def rotate_backups():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    if LATEST_BACKUP.exists():
        if PREVIOUS_BACKUP.exists():
            PREVIOUS_BACKUP.unlink()

        LATEST_BACKUP.rename(PREVIOUS_BACKUP)


def create_backup(force=False):
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные трансляции. Backup отложен.",
        }

    manifest = load_manifest()
    current_hash = calculate_content_hash()

    if not force and manifest.get("last_content_hash") == current_hash and LATEST_BACKUP.exists():
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

    manifest["last_backup_at"] = now_iso()
    manifest["last_content_hash"] = current_hash
    save_manifest(manifest)

    return {
        "ok": True,
        "skipped": False,
        "path": str(LATEST_BACKUP),
        "size": LATEST_BACKUP.stat().st_size if LATEST_BACKUP.exists() else 0,
    }


def safe_remove_path(path):
    path = Path(path)

    if not path.exists():
        return 0

    count = 0

    if path.is_file():
        path.unlink()
        return 1

    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
                count += 1
            elif child.is_dir():
                child.rmdir()
        except Exception:
            pass

    try:
        path.rmdir()
    except Exception:
        pass

    return count


def cleanup_queue():
    queue_root = PROJECT_ROOT / "queue"

    if not queue_root.exists():
        return 0

    removed = 0

    for channel_dir in queue_root.iterdir():
        if not channel_dir.is_dir():
            continue

        for item in channel_dir.iterdir():
            # active.mp4 can be used by a running/just-finished stream. Be conservative.
            if item.name == "active.mp4":
                continue

            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                    removed += 1
                elif item.is_dir():
                    removed += safe_remove_path(item)
            except Exception:
                pass

    return removed


def cleanup_temp():
    removed = 0

    for path in CLEAN_PATHS:
        removed += safe_remove_path(path)

    removed += cleanup_queue()

    # Recreate expected dirs.
    (PROJECT_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "cache").mkdir(parents=True, exist_ok=True)

    return removed


def run_cleanup():
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные трансляции. Очистка отложена.",
            "removed": 0,
        }

    removed = cleanup_temp()

    manifest = load_manifest()
    manifest["last_cleanup_at"] = now_iso()
    save_manifest(manifest)

    return {
        "ok": True,
        "skipped": False,
        "removed": removed,
    }


def run_maintenance(force_backup=False):
    if not maintenance_allowed():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Есть активные трансляции. Обслуживание отложено.",
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

    for path in [LATEST_BACKUP, PREVIOUS_BACKUP]:
        if path.exists():
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

    return backups


def format_maintenance_report(result):
    if result.get("skipped"):
        return f"🟡 Обслуживание отложено\n\n{result.get('reason', '')}"

    lines = [
        "🧹 Обслуживание завершено",
        "",
    ]

    cleanup = result.get("cleanup") or {}
    backup = result.get("backup") or {}

    if cleanup:
        if cleanup.get("skipped"):
            lines.append(f"🟡 Очистка: {cleanup.get('reason')}")
        else:
            lines.append(f"✅ Очистка: удалено файлов {cleanup.get('removed', 0)}")

    if backup:
        if backup.get("skipped"):
            lines.append(f"🟡 Backup: {backup.get('reason')}")
        else:
            lines.append(f"✅ Backup: {backup.get('path')}")

    return "\n".join(lines)
