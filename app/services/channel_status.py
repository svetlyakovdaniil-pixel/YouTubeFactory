from pathlib import Path

from app.services.channel_library import ChannelLibrary


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"
SYSTEMD_DIR = Path("/etc/systemd/system")


def safe_service_slug(name):
    import re

    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", slug)
    slug = slug.strip("-")
    return slug or "channel"


def service_name(channel):
    if channel == "Cosmic Slumber":
        return "youtubefactory-radio-cosmic"

    return f"youtubefactory-radio-{safe_service_slug(channel)}"


def service_exists(channel):
    return (SYSTEMD_DIR / f"{service_name(channel)}.service").exists()


def runtime_flag_exists(channel):
    return (PROJECT_ROOT / "runtime" / f"{channel}.running").exists()


def youtube_connected(channel):
    youtube_dir = LIBRARY_ROOT / channel / "youtube"
    return (
        (youtube_dir / "client_secret.json").exists()
        and (youtube_dir / "token.json").exists()
    )


def build_channel_status(channel, systemd_active=False):
    library = ChannelLibrary(channel)

    config = library.get_config()
    state = library.get_state()

    music_files = library.list_music()
    loop_videos = library.list_loop_videos()
    image_files = library.list_images()

    music_ready = len(music_files) > 0
    video_ready = len(loop_videos) > 0
    youtube_ready = youtube_connected(channel)
    service_ok = service_exists(channel)
    paused = bool(state.get("paused", False))

    effectively_running = (
        bool(systemd_active)
        and bool(state.get("running", False))
        and runtime_flag_exists(channel)
        and not paused
    )

    missing = []

    if not music_ready:
        missing.append("добавить музыку")

    if not video_ready:
        missing.append("добавить видео")

    if not youtube_ready:
        missing.append("подключить YouTube")

    if not service_ok:
        missing.append("восстановить systemd-сервис")

    if paused:
        missing.append("сбросить аварийную остановку")

    ready = (
        music_ready
        and video_ready
        and youtube_ready
        and service_ok
        and not paused
    )

    can_start = (
        ready
        and not effectively_running
    )

    if paused:
        status_label = "🛑 Требуется вмешательство"
        status_kind = "paused"
    elif effectively_running:
        status_label = "🟢 Эфир запущен"
        status_kind = "running"
    else:
        status_label = "🔴 Эфир остановлен"
        status_kind = "stopped"

    return {
        "channel": channel,
        "config": config,
        "state": state,
        "music_files": music_files,
        "loop_videos": loop_videos,
        "image_files": image_files,
        "music_ready": music_ready,
        "video_ready": video_ready,
        "youtube_ready": youtube_ready,
        "service_ok": service_ok,
        "paused": paused,
        "effectively_running": effectively_running,
        "ready": ready,
        "can_start": can_start,
        "missing": missing,
        "status_label": status_label,
        "status_kind": status_kind,
    }
