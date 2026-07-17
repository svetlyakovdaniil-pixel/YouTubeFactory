import fcntl
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.channel_library import ChannelLibrary
from app.services.vod_job_service import VODJobService


RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOG_DIR = PROJECT_ROOT / "logs" / "vod"

POLL_SECONDS = 60
ERROR_RETRY_SECONDS = 30 * 60
MIN_AVAILABLE_MEMORY_MB = 900
MIN_FREE_DISK_GB = 6

GLOBAL_LOCK_PATH = RUNTIME_DIR / "vod-render.lock"


def log(channel, message):
    timestamp = datetime.now().astimezone().isoformat()
    line = f"{timestamp} [{channel}] {message}"

    print(line, flush=True)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{channel}.log"

    with open(path, "a", encoding="utf-8") as file:
        file.write(line + "\n")


def available_memory_mb():
    values = {}

    with open("/proc/meminfo", encoding="utf-8") as file:
        for line in file:
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])

    return int(values.get("MemAvailable", 0) / 1024)


def free_disk_gb():
    stat = __import__("shutil").disk_usage(PROJECT_ROOT)
    return stat.free / (1024 ** 3)


def parse_publish_time(value):
    try:
        hour, minute = str(value).strip().split(":", 1)
        return int(hour), int(minute)
    except Exception:
        return 12, 0


def local_now(config):
    timezone_name = config.get(
        "timezone",
        "Asia/Almaty",
    )

    return datetime.now(
        ZoneInfo(timezone_name)
    )


def publication_is_due(config, now):
    hour, minute = parse_publish_time(
        config.get(
            "publish_time",
            "12:00",
        )
    )

    scheduled = now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    return now >= scheduled


def acquire_global_lock():
    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = open(
        GLOBAL_LOCK_PATH,
        "a+",
        encoding="utf-8",
    )

    try:
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX
            | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        handle.close()
        return None

    return handle


def run(channel):
    library = ChannelLibrary(channel)
    job = VODJobService(channel)

    last_error_attempt = 0.0

    log(channel, "VOD worker started.")

    while True:
        try:
            config = library.get_vod_config()

            if not config.get("enabled"):
                time.sleep(POLL_SECONDS)
                continue

            now = local_now(config)
            local_date = now.date().isoformat()

            if not publication_is_due(
                config,
                now,
            ):
                time.sleep(POLL_SECONDS)
                continue

            existing = (
                job.already_published_today(
                    local_date
                )
            )

            if existing:
                time.sleep(POLL_SECONDS)
                continue

            if (
                last_error_attempt
                and time.monotonic()
                - last_error_attempt
                < ERROR_RETRY_SECONDS
            ):
                time.sleep(POLL_SECONDS)
                continue

            memory_mb = available_memory_mb()
            disk_gb = free_disk_gb()

            if memory_mb < MIN_AVAILABLE_MEMORY_MB:
                log(
                    channel,
                    "Waiting for memory: "
                    f"{memory_mb} MB available, "
                    f"required {MIN_AVAILABLE_MEMORY_MB} MB.",
                )
                time.sleep(5 * 60)
                continue

            if disk_gb < MIN_FREE_DISK_GB:
                log(
                    channel,
                    "Waiting for disk space: "
                    f"{disk_gb:.1f} GB free, "
                    f"required {MIN_FREE_DISK_GB} GB.",
                )
                time.sleep(5 * 60)
                continue

            lock_handle = acquire_global_lock()

            if lock_handle is None:
                time.sleep(POLL_SECONDS)
                continue

            try:
                log(
                    channel,
                    "Starting scheduled VOD job.",
                )

                result = job.run()

                publish = result[
                    "publish_result"
                ]

                log(
                    channel,
                    "VOD published successfully: "
                    f"{publish['youtube_url']}",
                )

                last_error_attempt = 0.0

            finally:
                fcntl.flock(
                    lock_handle.fileno(),
                    fcntl.LOCK_UN,
                )
                lock_handle.close()

        except KeyboardInterrupt:
            log(channel, "VOD worker stopped.")
            break

        except Exception:
            last_error_attempt = time.monotonic()

            log(
                channel,
                "VOD job failed:\n"
                + traceback.format_exc(),
            )

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: vod_worker.py <channel>"
        )

    run(sys.argv[1])
