from pathlib import Path
import subprocess
import streamlit as st


st.set_page_config(
    page_title="Live Streams",
    page_icon="📡",
    layout="wide",
)

st.title("📡 Live Dashboard")


RUNTIME_DIR = Path("/opt/youtubefactory/runtime")
LOG_FILE = Path("/opt/youtubefactory/logs/live_worker.log")
OUTPUT_DIR = Path("/opt/youtubefactory/output")
QUEUE_ROOT = Path("/opt/youtubefactory/queue")
CHANNEL_NAME = "Space Dreams"
QUEUE_DIR = QUEUE_ROOT / CHANNEL_NAME


def run_command(command):

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout + result.stderr


def is_service_active(service):

    result = subprocess.run(
        f"systemctl is-active {service}",
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip() == "active"


def get_last_live_url():

    if not LOG_FILE.exists():
        return None

    lines = LOG_FILE.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    for line in reversed(lines):
        if "Live started:" in line:
            return line.split("Live started:", 1)[1].strip()

    return None


def get_recent_logs():

    if not LOG_FILE.exists():
        return "Логов пока нет."

    lines = LOG_FILE.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    return "\n".join(lines[-120:])


def get_latest_video():

    videos = sorted(
        OUTPUT_DIR.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not videos:
        return None

    return videos[0]


def get_queue_videos():

    if not QUEUE_DIR.exists():
        return []

    return sorted(
        QUEUE_DIR.glob("*.mp4"),
        key=lambda p: p.name,
    )


def format_size(path):

    size_mb = path.stat().st_size / 1024 / 1024

    return f"{size_mb:.1f} MB"


st.subheader("Состояние")

col1, col2, col3 = st.columns(3)

with col1:
    if is_service_active("youtubefactory-worker"):
        st.success("🟢 Worker работает")
    else:
        st.error("🔴 Worker остановлен")

with col2:
    last_url = get_last_live_url()

    if last_url:
        st.success("🟢 Последний эфир найден")
        st.link_button(
            "Открыть эфир",
            last_url,
            use_container_width=True,
        )
    else:
        st.warning("Эфир пока не найден")

with col3:
    latest_video = get_latest_video()

    if latest_video:
        st.success("🎬 Последнее видео")
        st.write(latest_video.name)
    else:
        st.warning("Видео пока нет")


st.divider()

st.subheader("Очередь эфиров")

queue_videos = get_queue_videos()

if queue_videos:

    st.write(f"Видео в очереди: **{len(queue_videos)}**")

    for video in queue_videos:

        with st.container(border=True):

            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                if video.name == "active.mp4":
                    st.markdown(f"### 🟢 Сейчас в эфире: `{video.name}`")
                else:
                    st.markdown(f"### ⏭ Следующее: `{video.name}`")

                st.caption(str(video))

            with col2:
                st.write(format_size(video))

            with col3:
                st.write("MP4")

else:
    st.warning("Очередь пока пустая.")


st.divider()

st.subheader("Управление worker")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button(
        "▶ Запустить worker",
        use_container_width=True,
    ):
        run_command("systemctl start youtubefactory-worker")
        st.success("Worker запущен")
        st.rerun()

with col2:
    if st.button(
        "🔄 Перезапустить worker",
        use_container_width=True,
    ):
        run_command("systemctl restart youtubefactory-worker")
        st.success("Worker перезапущен")
        st.rerun()

with col3:
    if st.button(
        "■ Остановить worker",
        use_container_width=True,
    ):
        run_command("systemctl stop youtubefactory-worker")
        st.warning("Worker остановлен")
        st.rerun()


st.divider()

st.subheader("Последнее созданное видео")

latest_video = get_latest_video()

if latest_video:
    st.video(str(latest_video))
    st.caption(str(latest_video))
else:
    st.info("Пока нет созданных видео.")


st.divider()

st.subheader("Логи автоэфира")

if st.button(
    "🔄 Обновить логи",
    use_container_width=True,
):
    st.rerun()

st.code(
    get_recent_logs(),
    language="bash",
)


st.divider()

st.subheader("Диагностика")

col1, col2 = st.columns(2)

with col1:
    if st.button(
        "📊 Статус systemd worker",
        use_container_width=True,
    ):
        st.code(
            run_command(
                "systemctl status youtubefactory-worker --no-pager"
            ),
            language="bash",
        )

with col2:
    if st.button(
        "🎥 Активные FFmpeg процессы",
        use_container_width=True,
    ):
        st.code(
            run_command(
                "ps aux | grep ffmpeg"
            ),
            language="bash",
        )