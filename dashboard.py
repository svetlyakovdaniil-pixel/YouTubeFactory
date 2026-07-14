import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from app.services.channel_library import ChannelLibrary
from app.services.telegram_notifier import TelegramNotifier
from app.services.channel_status import build_channel_status
from app.services.channel_control import stop_channel_fully
from app.services.event_log import read_events, clear_events
from app.services.error_advisor import analyze_error, format_advice
from app.services.recovery_manager import recover_channel, format_recovery_report
from app.services.preflight_manager import format_preflight_report
from app.services.server_diagnostics import format_server_diagnostics
from app.services.maintenance_manager import list_backups, run_maintenance, format_maintenance_report
from app.services.metadata_manager import ensure_metadata_templates, templates_to_text, text_to_templates
from app.services.media_pipeline import prepare_loop_video
from app.ui.youtube_page import render as render_youtube_page


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"
SYSTEMD_DIR = Path("/etc/systemd/system")
LOG_FILE = PROJECT_ROOT / "logs" / "live_worker.log"
TELEGRAM_EVENTS_LOG = PROJECT_ROOT / "logs" / "telegram_events.log"


st.set_page_config(
    page_title="YouTube Factory",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {display: none;}
    [data-testid="collapsedControl"] {display: none;}
    .block-container {padding-top: 2rem; max-width: 1180px;}
    button {border-radius: 10px !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def safe_service_slug(name):
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", slug)
    slug = slug.strip("-")
    return slug or "channel"


def service_name(channel):
    if channel == "Cosmic Slumber":
        return "youtubefactory-radio-cosmic"

    return f"youtubefactory-radio-{safe_service_slug(channel)}"


def service_exists(channel):
    service_path = SYSTEMD_DIR / f"{service_name(channel)}.service"
    return service_path.exists()


def runtime_flag_exists(channel):
    return (PROJECT_ROOT / "runtime" / f"{channel}.running").exists()


def youtube_connected(channel):
    youtube_dir = LIBRARY_ROOT / channel / "youtube"
    return (
        (youtube_dir / "client_secret.json").exists()
        and (youtube_dir / "token.json").exists()
    )


def is_active(channel):
    code, stdout, stderr = run_cmd(
        ["systemctl", "is-active", service_name(channel)]
    )
    return stdout == "active"


def start_channel(channel):
    return run_cmd(["systemctl", "start", service_name(channel)])


def stop_channel(channel):
    result = stop_channel_fully(channel)

    return (
        result.get("code", 1),
        result.get("stdout", ""),
        result.get("stderr", ""),
    )


def disable_channel(channel):
    return run_cmd(["systemctl", "disable", service_name(channel)])


def list_channels():
    if not LIBRARY_ROOT.exists():
        return []

    return sorted(
        path.name
        for path in LIBRARY_ROOT.iterdir()
        if path.is_dir() and (path / "config.json").exists()
    )


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_systemd_service(channel):
    name = service_name(channel)
    service_path = SYSTEMD_DIR / f"{name}.service"

    content = f"""[Unit]
Description=YouTube Factory Radio - {channel}
After=network.target

[Service]
User=root
WorkingDirectory=/opt/youtubefactory
ExecStartPre=/usr/bin/mkdir -p /opt/youtubefactory/runtime
ExecStartPre=/usr/bin/touch "/opt/youtubefactory/runtime/{channel}.running"
ExecStart=/opt/youtubefactory/venv/bin/python /opt/youtubefactory/workers/live_worker.py "{channel}"
ExecStopPost=/usr/bin/rm -f "/opt/youtubefactory/runtime/{channel}.running"
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
"""

    with open(service_path, "w", encoding="utf-8") as f:
        f.write(content)

    run_cmd(["systemctl", "daemon-reload"])
    run_cmd(["systemctl", "enable", name])


def create_channel(name, title, description, duration_hours):
    name = name.strip()

    if not name:
        raise ValueError("Название канала не может быть пустым.")

    root = LIBRARY_ROOT / name

    if root.exists():
        raise ValueError("Такой канал уже существует.")

    (root / "music").mkdir(parents=True, exist_ok=True)
    (root / "loop_videos").mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "youtube").mkdir(parents=True, exist_ok=True)

    config = {
        "name": name,
        "enabled": True,
        "stream_duration_hours": int(duration_hours),
        "privacy": "public",
        "title_template": title.strip() or f"{name} Radio",
        "description": description.strip(),
        "made_for_kids": False,
        "youtube_autostart": True,
        "youtube_autostop": True,
    }

    state = {
        "running": False,
        "watch_url": "",
        "started_at": "",
        "stream_duration_hours": int(duration_hours),
        "current_track": "",
        "track_index": 0,
        "last_error": "",
    }

    write_json(root / "config.json", config)
    write_json(root / "state.json", state)

    create_systemd_service(name)


def delete_channel(channel):
    stop_channel(channel)
    disable_channel(channel)

    service_path = SYSTEMD_DIR / f"{service_name(channel)}.service"

    if service_path.exists():
        service_path.unlink()

    run_cmd(["systemctl", "daemon-reload"])

    root = LIBRARY_ROOT / channel

    if root.exists():
        shutil.rmtree(root)


def file_sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def uploaded_file_sha256(uploaded_file):
    return hashlib.sha256(
        bytes(uploaded_file.getbuffer())
    ).hexdigest()


def find_duplicate_file(uploaded_file, target_dir):
    target_dir = Path(target_dir)

    if not target_dir.exists():
        return None

    uploaded_size = int(
        getattr(uploaded_file, "size", 0) or 0
    )
    uploaded_hash = uploaded_file_sha256(
        uploaded_file
    )

    for existing_path in target_dir.iterdir():
        if not existing_path.is_file():
            continue

        try:
            if (
                uploaded_size
                and existing_path.stat().st_size
                != uploaded_size
            ):
                continue

            if (
                file_sha256(existing_path)
                == uploaded_hash
            ):
                return existing_path
        except OSError:
            continue

    return None


def save_uploaded_file(uploaded_file, target_dir):
    target_dir = Path(target_dir)
    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    duplicate = find_duplicate_file(
        uploaded_file,
        target_dir,
    )

    if duplicate is not None:
        return duplicate, False

    original_name = Path(
        uploaded_file.name
    ).name
    original_path = Path(original_name)
    stem = original_path.stem
    suffix = original_path.suffix

    target_path = target_dir / original_name
    counter = 2

    while target_path.exists():
        target_path = (
            target_dir
            / f"{stem}_{counter}{suffix}"
        )
        counter += 1

    with open(target_path, "wb") as file:
        file.write(uploaded_file.getbuffer())

    return target_path, True


def delete_file(path):
    path = Path(path)

    if path.exists() and path.is_file():
        path.unlink()


def format_size(path):
    size = Path(path).stat().st_size

    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.2f} ГБ"

    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} МБ"

    if size >= 1024:
        return f"{size / 1024:.1f} КБ"

    return f"{size} Б"


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def elapsed_seconds(started_at):
    started = parse_datetime(started_at)

    if not started:
        return None

    now = datetime.now(timezone.utc)
    return max(0, int((now - started).total_seconds()))


def remaining_seconds(started_at, duration_hours):
    elapsed = elapsed_seconds(started_at)

    if elapsed is None:
        return None

    total = int(duration_hours) * 60 * 60
    return max(0, total - elapsed)


def format_seconds(seconds):
    if seconds is None:
        return "—"

    seconds = max(0, int(seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def clean_track_name(name):
    for suffix in [".mp3", ".wav", ".m4a", ".aac", ".flac"]:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]

    return name


def read_logs(lines=120):
    if not LOG_FILE.exists():
        return "Журнал пока пуст."

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()

    return "".join(content[-lines:])


def read_telegram_events(lines=80):
    if not TELEGRAM_EVENTS_LOG.exists():
        return "История Telegram пока пустая."

    with open(TELEGRAM_EVENTS_LOG, "r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()

    return "".join(content[-lines:])


def format_event_time(value):
    if not value:
        return "—"

    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return value


def event_icon(level):
    return {
        "success": "🟢",
        "info": "ℹ️",
        "warning": "🟡",
        "error": "🔴",
        "raw": "📄",
    }.get(level, "ℹ️")


st.title("📡 YouTube Factory")

channels = list_channels()

top_a, top_b = st.columns([3, 1])

with top_a:
    if channels:
        selected_channel = st.selectbox("Канал", channels)
    else:
        selected_channel = None

with top_b:
    if st.button("➕ Добавить канал", use_container_width=True):
        st.session_state["show_add_channel"] = True

if st.session_state.get("show_add_channel"):
    st.divider()
    st.subheader("➕ Новый канал")

    with st.form("create_channel_form"):
        new_name = st.text_input("Название канала", placeholder="Например: HipHop 90")
        new_title = st.text_input("Название эфира на YouTube", placeholder="HipHop 90 Radio")
        new_description = st.text_area("Описание эфира", height=140)
        new_duration = st.radio("Длительность эфира", [6, 12], index=1, horizontal=True)

        c1, c2 = st.columns(2)

        with c1:
            create_pressed = st.form_submit_button("Создать канал", use_container_width=True)

        with c2:
            cancel_pressed = st.form_submit_button("Отмена", use_container_width=True)

    if cancel_pressed:
        st.session_state["show_add_channel"] = False
        st.rerun()

    if create_pressed:
        try:
            create_channel(
                name=new_name,
                title=new_title,
                description=new_description,
                duration_hours=new_duration,
            )

            st.session_state["show_add_channel"] = False
            st.success("Канал создан.")
            st.rerun()

        except Exception as e:
            st.error(str(e))

if not selected_channel:
    st.warning("Каналов пока нет. Создай первый канал.")
    st.stop()

library = ChannelLibrary(selected_channel)

config = library.get_config()
state = library.get_state()

active = is_active(selected_channel)
channel_status = build_channel_status(
    selected_channel,
    systemd_active=active,
)

metadata_config = ensure_metadata_templates(selected_channel)
channel_status = build_channel_status(
    selected_channel,
    systemd_active=active,
)

config = channel_status["config"]
state = channel_status["state"]

music_files = channel_status["music_files"]
loop_videos = channel_status["loop_videos"]
image_files = channel_status["image_files"]

music_ready = channel_status["music_ready"]
video_ready = channel_status["video_ready"]
youtube_ready = channel_status["youtube_ready"]
service_ok = channel_status["service_ok"]
paused = channel_status["paused"]
effectively_running = channel_status["effectively_running"]
channel_ready = channel_status["ready"]
can_start = channel_status["can_start"]
missing = channel_status["missing"]

duration_hours = int(config.get("stream_duration_hours", 12))
started_at = state.get("started_at")

if effectively_running:
    elapsed = elapsed_seconds(started_at)
    remaining = remaining_seconds(started_at, duration_hours)
else:
    elapsed = None
    remaining = None

total_seconds = duration_hours * 60 * 60

progress_value = 0

if elapsed is not None and total_seconds > 0:
    progress_value = min(1.0, max(0.0, elapsed / total_seconds))

st.divider()

st.subheader("Готовность канала")

r1, r2, r3, r4 = st.columns(4)

with r1:
    st.metric(
        "Музыка",
        f"{len(music_files)}",
        "готово" if music_ready else "нет файлов",
    )

with r2:
    st.metric(
        "Видео",
        f"{len(loop_videos)}",
        "готово" if video_ready else "нет файлов",
    )

with r3:
    st.metric(
        "YouTube",
        "✅" if youtube_ready else "❌",
        "подключен" if youtube_ready else "не подключен",
    )

with r4:
    st.metric(
        "Systemd",
        "✅" if service_ok else "❌",
        "есть" if service_ok else "отсутствует",
    )

if paused:
    st.error("🛑 Канал остановлен после критической ошибки. Требуется вмешательство.")

if channel_ready:
    st.success("🟢 Канал готов к запуску.")
else:
    st.error("🔴 Канал не готов к запуску.")
    st.write("Нужно: " + ", ".join(missing))

st.divider()

col_status, col_control = st.columns([2, 1])

with col_status:
    st.header(selected_channel)

    if channel_status["status_kind"] == "paused":
        st.error(channel_status["status_label"])
    elif channel_status["status_kind"] == "running":
        st.success(channel_status["status_label"])
    else:
        st.error(channel_status["status_label"])

    st.write(f"Режим: **{duration_hours} часов**")
    st.write(f"Systemd-сервис: **{'есть' if service_ok else 'отсутствует'}**")

    if paused and state.get("last_error"):
        st.warning("Канал остановлен из-за критической ошибки.")
        st.info(format_advice(state["last_error"]))

        report, recovery_result = format_recovery_report(selected_channel)

        with st.expander("🔧 Проверка восстановления", expanded=True):
            st.text(report)

        with st.expander("Технические детали ошибки"):
            st.code(state["last_error"])

with col_control:
    if not service_ok:
        st.error("Systemd-сервис для этого канала не найден.")

        if st.button("🔧 Восстановить сервис", use_container_width=True):
            try:
                create_systemd_service(selected_channel)
                st.success("Сервис восстановлен.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    else:
        if paused:
            st.error("Канал на паузе после критической ошибки.")

            if st.button("🔧 Восстановить канал", use_container_width=True):
                recovery = recover_channel(selected_channel)

                if recovery.get("ok"):
                    st.success(recovery["message"])
                    st.rerun()
                else:
                    st.error(recovery["message"])

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "▶ Запустить",
                use_container_width=True,
                disabled=not can_start,
            ):
                code, stdout, stderr = start_channel(selected_channel)

                if code == 0:
                    st.success("Запускаю эфир.")
                    st.rerun()
                else:
                    st.error(stderr or stdout)

        with c2:
            if st.button("■ Остановить", use_container_width=True):
                code, stdout, stderr = stop_channel(selected_channel)

                if code == 0:
                    st.success(
                        stdout
                        or "Эфир полностью остановлен."
                    )
                    st.rerun()
                else:
                    st.error(stderr or stdout)

        if paused:
            st.caption("Сначала нажмите «Восстановить канал».")
        elif not can_start and not effectively_running:
            st.caption("Запуск станет доступен, когда канал будет полностью готов.")

    if state.get("watch_url"):
        st.link_button(
            "Открыть YouTube",
            state["watch_url"],
            use_container_width=True,
        )

st.divider()

m1, m2, m3 = st.columns(3)

with m1:
    current_track = state.get("current_track") if effectively_running else ""
    st.metric("Текущий трек", current_track or "—")

with m2:
    st.metric("Идёт", format_seconds(elapsed))

with m3:
    st.metric("Осталось", format_seconds(remaining))

st.progress(progress_value)

st.caption(f"Прогресс эфира: {int(progress_value * 100)}%")

st.divider()

tab_music, tab_visuals, tab_images, tab_youtube, tab_metadata, tab_telegram, tab_events, tab_preflight, tab_server, tab_backup, tab_settings, tab_logs, tab_danger = st.tabs(
    [
        f"🎵 Музыка ({len(music_files)})",
        f"🎥 Видео ({len(loop_videos)})",
        f"🖼 Превью ({len(image_files)})",
        "📺 YouTube",
        "📝 Названия",
        "📨 Telegram",
        "🧾 События",
        "🛡 Проверка",
        "🖥 Сервер",
        "💾 Backup",
        "⚙ Настройки",
        "📜 Журнал",
        "🗑 Управление каналом",
    ]
)

with tab_music:
    st.subheader("Музыка")

    music_uploader_key = (
        f"music_uploader_version_{selected_channel}"
    )
    music_uploader_version = (
        st.session_state.get(
            music_uploader_key,
            0,
        )
    )

    uploaded_music = st.file_uploader(
        "Загрузить музыку",
        type=[
            "mp3",
            "wav",
            "m4a",
            "aac",
            "flac",
        ],
        accept_multiple_files=True,
        key=(
            f"music_uploader_"
            f"{selected_channel}_"
            f"{music_uploader_version}"
        ),
    )

    if uploaded_music:
        added_count = 0
        duplicate_count = 0

        for file in uploaded_music:
            _, created = save_uploaded_file(
                file,
                library.music_dir,
            )

            if created:
                added_count += 1
            else:
                duplicate_count += 1

        if added_count:
            st.success(
                f"Новых музыкальных файлов: "
                f"{added_count}."
            )

        if duplicate_count:
            st.info(
                f"Пропущено существующих копий: "
                f"{duplicate_count}."
            )

        st.session_state[
            music_uploader_key
        ] = music_uploader_version + 1

        st.rerun()

    for file in music_files:
        col_name, col_size, col_delete = st.columns([6, 1, 1])

        with col_name:
            st.write(clean_track_name(file.name))

        with col_size:
            st.caption(format_size(file))

        with col_delete:
            if st.button("Удалить", key=f"delete_music_{file.resolve()}"):
                delete_file(file)
                st.rerun()

with tab_visuals:
    st.subheader("Видео для эфира")

    video_uploader_key = (
        f"video_uploader_version_{selected_channel}"
    )
    video_uploader_version = (
        st.session_state.get(
            video_uploader_key,
            0,
        )
    )

    uploaded_video = st.file_uploader(
        "Загрузить видео",
        type=[
            "mp4",
            "mov",
            "webm",
            "mkv",
        ],
        accept_multiple_files=True,
        key=(
            f"video_uploader_"
            f"{selected_channel}_"
            f"{video_uploader_version}"
        ),
    )

    if uploaded_video:
        prepared_count = 0
        repaired_existing_count = 0
        duplicate_count = 0
        failed_files = []

        with st.spinner(
            "Загрузка и подготовка видео..."
        ):
            for file in uploaded_video:
                try:
                    source_path, created = (
                        save_uploaded_file(
                            file,
                            library.loop_videos_dir,
                        )
                    )

                    ready_path = (
                        library.loop_videos_ready_dir
                        / (
                            f"{source_path.stem}"
                            f"_stream_ready.mp4"
                        )
                    )

                    if not created and ready_path.exists():
                        duplicate_count += 1
                        continue

                    result = prepare_loop_video(
                        selected_channel,
                        source_path,
                    )

                    if result.get("ok", False):
                        if created:
                            prepared_count += 1
                        else:
                            repaired_existing_count += 1
                    else:
                        failed_files.append(
                            f"{file.name}: "
                            f"{result.get('error', 'неизвестная ошибка')}"
                        )
                except Exception as exc:
                    failed_files.append(
                        f"{file.name}: {exc}"
                    )

        if prepared_count:
            st.success(
                f"Новых видео загружено и подготовлено: "
                f"{prepared_count}."
            )

        if repaired_existing_count:
            st.success(
                f"Подготовлено ранее загруженных видео: "
                f"{repaired_existing_count}."
            )

        if duplicate_count:
            st.info(
                f"Пропущено полностью готовых копий: "
                f"{duplicate_count}."
            )

        if failed_files:
            st.error(
                "Не удалось подготовить некоторые видео:"
            )

            for item in failed_files:
                st.write(f"- {item}")
        else:
            st.session_state[
                video_uploader_key
            ] = video_uploader_version + 1
            st.rerun()

    for file in loop_videos:
        st.markdown("---")

        col_info, col_delete = st.columns([6, 1])

        with col_info:
            st.write(f"**{file.name}**")
            st.caption(format_size(file))
            st.video(str(file))

        with col_delete:
            if st.button("Удалить", key=f"delete_video_{file.resolve()}"):
                delete_file(file)
                st.rerun()

with tab_images:
    st.subheader("Превью / обложки")

    st.info(
        "Сюда загружаются изображения для будущих YouTube-превью. "
        "Рекомендуемый размер: 1280×720, формат JPG или PNG."
    )

    image_uploader_key = (
        f"image_uploader_version_{selected_channel}"
    )
    image_uploader_version = (
        st.session_state.get(
            image_uploader_key,
            0,
        )
    )

    uploaded_images = st.file_uploader(
        "Загрузить изображения превью",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        accept_multiple_files=True,
        key=(
            f"image_uploader_"
            f"{selected_channel}_"
            f"{image_uploader_version}"
        ),
    )

    if uploaded_images:
        added_count = 0
        duplicate_count = 0

        for file in uploaded_images:
            _, created = save_uploaded_file(
                file,
                library.images_dir,
            )

            if created:
                added_count += 1
            else:
                duplicate_count += 1

        if added_count:
            st.success(
                f"Новых изображений: "
                f"{added_count}."
            )

        if duplicate_count:
            st.info(
                f"Пропущено существующих копий: "
                f"{duplicate_count}."
            )

        st.session_state[
            image_uploader_key
        ] = image_uploader_version + 1

        st.rerun()

    if not image_files:
        st.warning("Изображения превью ещё не загружены.")

    for file in image_files:
        st.markdown("---")

        col_info, col_delete = st.columns([6, 1])

        with col_info:
            st.write(f"**{file.name}**")
            st.caption(format_size(file))
            st.image(str(file), use_container_width=True)

        with col_delete:
            if st.button("Удалить", key=f"delete_image_{file.resolve()}"):
                delete_file(file)
                st.rerun()

with tab_youtube:
    render_youtube_page(selected_channel)



with tab_metadata:
    st.subheader("Названия и описания эфиров")

    st.info(
        "Перед каждым новым эфиром система случайно выбирает одно название и одно описание. "
        "Последний использованный вариант не повторяется два эфира подряд. "
        "Разделитель между вариантами: строка с тремя дефисами ---"
    )

    metadata_config = ensure_metadata_templates(selected_channel)

    title_templates_text = templates_to_text(
        metadata_config.get("title_templates", [])
    )

    description_templates_text = templates_to_text(
        metadata_config.get("description_templates", [])
    )

    with st.form("metadata_templates_form"):
        title_templates_input = st.text_area(
            "Шаблоны названий",
            value=title_templates_text,
            height=220,
        )

        description_templates_input = st.text_area(
            "Шаблоны описаний",
            value=description_templates_text,
            height=420,
        )

        save_metadata = st.form_submit_button(
            "Сохранить шаблоны",
            use_container_width=True,
        )

    if save_metadata:
        config = library.get_config()
        config["title_templates"] = text_to_templates(title_templates_input)
        config["description_templates"] = text_to_templates(description_templates_input)
        library.save_config(config)

        st.success("Шаблоны сохранены.")
        st.rerun()

    st.divider()

    st.write("Последнее использованное название:")
    st.code(metadata_config.get("last_title_template", "—") or "—")

    st.write("Последнее использованное описание:")
    st.code(metadata_config.get("last_description_template", "—") or "—")


with tab_telegram:
    st.subheader("Telegram уведомления")

    notifier = TelegramNotifier()
    telegram_config = notifier.load_config()

    if (
        telegram_config.get("enabled")
        and telegram_config.get("bot_token")
        and telegram_config.get("chat_id")
    ):
        st.success("🟢 Telegram подключен")
    else:
        st.warning("🟡 Telegram не подключен")

    st.info(
        "Telegram нужен для уведомлений о запуске, остановке и критических ошибках. "
        "Если указать Web Interface URL, в каждое уведомление будет добавляться ссылка на панель управления."
    )

    with st.form("telegram_settings_form"):
        enabled = st.checkbox(
            "Включить Telegram уведомления",
            value=bool(telegram_config.get("enabled", False)),
        )

        bot_token = st.text_input(
            "Bot Token",
            value=telegram_config.get("bot_token", ""),
            type="password",
            placeholder="123456789:AA...",
        )

        chat_id = st.text_input(
            "Chat ID",
            value=telegram_config.get("chat_id", ""),
            placeholder="270342548",
        )

        interface_url = st.text_input(
            "Web Interface URL",
            value=telegram_config.get("interface_url", ""),
            placeholder="http://2.56.177.204:8501",
        )

        save_telegram = st.form_submit_button(
            "Сохранить Telegram настройки",
            use_container_width=True,
        )

    if save_telegram:
        TelegramNotifier.save_config(
            enabled=enabled,
            bot_token=bot_token,
            chat_id=chat_id,
            interface_url=interface_url,
        )

        st.success("Telegram настройки сохранены.")
        st.rerun()

    st.divider()

    if st.button("📤 Отправить тестовое сообщение", use_container_width=True):
        test_notifier = TelegramNotifier()

        result = test_notifier.send(
            text=(
                "🟢 YouTube Factory\n\n"
                f"Канал: {selected_channel}\n\n"
                "Тестовое сообщение отправлено успешно."
            ),
            channel=selected_channel,
            level="test",
        )

        if result.get("ok"):
            st.success("Тестовое сообщение отправлено.")
        else:
            st.error(result.get("error", "Не удалось отправить сообщение."))

    st.divider()

    st.subheader("История Telegram событий")

    if st.button("Обновить Telegram историю", use_container_width=True):
        st.rerun()

    st.code(read_telegram_events(80))



with tab_events:
    st.subheader("Журнал событий канала")

    e1, e2 = st.columns(2)

    with e1:
        if st.button("Обновить события", use_container_width=True):
            st.rerun()

    with e2:
        if st.button("Очистить события", use_container_width=True):
            clear_events(selected_channel)
            st.success("Журнал событий очищен.")
            st.rerun()

    events = read_events(selected_channel, limit=160)

    if not events:
        st.info("Событий пока нет.")
    else:
        for item in reversed(events):
            level = item.get("level", "info")
            message = item.get("message", "")
            created_at = format_event_time(item.get("time", ""))
            data = item.get("data", {}) or {}

            st.markdown(
                f"**{event_icon(level)} {created_at}**  \n"
                f"{message}"
            )

            if data:
                if data.get("error_title"):
                    st.warning(
                        f"Причина: {data.get('error_title')}\n\n"
                        f"Что произошло: {data.get('what_happened', '')}"
                    )

                    actions = data.get("recommended_actions", [])

                    if actions:
                        st.write("Что сделать:")

                        for idx, action in enumerate(actions, start=1):
                            st.write(f"{idx}. {action}")

                with st.expander("Детали"):
                    st.json(data)

            st.divider()



with tab_preflight:
    st.subheader("Preflight Check")

    report, preflight_result = format_preflight_report(selected_channel)

    if preflight_result["ok"]:
        st.success("🟢 Канал готов к запуску")
    else:
        st.error("🔴 Запуск запрещён до исправления ошибок")

    st.text(report)

    st.divider()

    if st.button("🔄 Повторить проверку", use_container_width=True):
        st.rerun()



with tab_server:
    st.subheader("Диагностика сервера")

    report, server_result = format_server_diagnostics()

    if server_result["ok"]:
        st.success("🟢 Сервер готов к работе")
    else:
        st.error("🔴 На сервере есть проблемы")

    st.text(report)

    st.divider()

    if st.button("🔄 Проверить сервер ещё раз", use_container_width=True):
        st.rerun()



with tab_backup:
    st.subheader("Backup и обслуживание")

    st.info(
        "Backup и очистка запускаются автоматически после завершения эфира, "
        "если нет активных трансляций. Хранятся только две копии: latest и previous."
    )

    backups = list_backups()

    if backups:
        for item in backups:
            st.write(f"**{item['name']}**")
            st.caption(f"Размер: {item['size']} bytes | UTC: {item['modified']}")
    else:
        st.warning("Резервных копий пока нет.")

    st.divider()

    if st.button("🧹 Запустить обслуживание сейчас", use_container_width=True):
        result = run_maintenance(force_backup=True)

        if result.get("skipped"):
            st.warning(format_maintenance_report(result))
        else:
            st.success(format_maintenance_report(result))

        st.rerun()

    st.divider()

    st.warning(
        "Восстановление backup лучше делать только при остановленных каналах. "
        "Кнопку восстановления добавим после финального теста, чтобы не рисковать текущей рабочей системой."
    )


with tab_settings:
    st.subheader("Настройки канала")

    new_duration = st.radio(
        "Длительность эфира",
        [6, 12],
        index=0 if duration_hours == 6 else 1,
        horizontal=True,
    )

    title_template = st.text_input(
        "Название эфира на YouTube",
        value=config.get("title_template", f"{selected_channel} Radio"),
    )

    description = st.text_area(
        "Описание эфира",
        value=config.get("description", ""),
        height=160,
    )

    st.info(
        "Фиксированные настройки YouTube: доступ — открытый, видео не для детей, "
        "автозапуск и автоостановка включены, качество — исходное без пережатия."
    )

    if st.button("Сохранить настройки", use_container_width=True):
        config["stream_duration_hours"] = int(new_duration)
        config["title_template"] = title_template
        config["description"] = description
        config["privacy"] = "public"
        config["made_for_kids"] = False
        config["youtube_autostart"] = True
        config["youtube_autostop"] = True

        library.save_config(config)

        st.success("Настройки сохранены.")
        st.rerun()

    if state.get("last_error"):
        st.divider()
        st.subheader("Последняя ошибка")
        st.code(state["last_error"])

with tab_logs:
    st.subheader("Журнал работы")

    if st.button("Обновить журнал", use_container_width=True):
        st.rerun()

    st.code(read_logs(140))

with tab_danger:
    st.subheader("Управление каналом")

    st.warning("Удаление канала удалит музыку, видео, настройки и systemd-сервис.")

    confirm = st.text_input(
        f"Чтобы удалить канал, напиши его название: {selected_channel}"
    )

    if st.button("Удалить канал", use_container_width=True):
        if confirm == selected_channel:
            delete_channel(selected_channel)
            st.success("Канал удалён.")
            st.rerun()
        else:
            st.error("Название введено неверно.")


if active and not st.session_state.get("show_add_channel"):
    time.sleep(10)
    st.rerun()