import subprocess
import streamlit as st


st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ Панель управления сервером")


def run_command(command):

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout + result.stderr


def is_active(service):

    result = subprocess.run(
        f"systemctl is-active {service}",
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip() == "active"


def status_card(title, service):

    active = is_active(service)

    if active:
        st.success(f"🟢 {title} работает")
    else:
        st.error(f"🔴 {title} остановлен")


services = {
    "Dashboard / Интерфейс": "youtubefactory",
    "Live Worker / Автоэфир": "youtubefactory-worker",
}


st.subheader("Состояние системы")

col1, col2 = st.columns(2)

with col1:
    status_card(
        "Dashboard",
        "youtubefactory",
    )

with col2:
    status_card(
        "Live Worker",
        "youtubefactory-worker",
    )


st.divider()

for title, service in services.items():

    st.subheader(title)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(
            "▶ Запустить",
            key=f"start_{service}",
            use_container_width=True,
        ):
            run_command(f"systemctl start {service}")
            st.success("Запущено")
            st.rerun()

    with col2:
        if st.button(
            "🔄 Перезапустить",
            key=f"restart_{service}",
            use_container_width=True,
        ):
            run_command(f"systemctl restart {service}")
            st.success("Перезапущено")
            st.rerun()

    with col3:
        if st.button(
            "■ Остановить",
            key=f"stop_{service}",
            use_container_width=True,
        ):
            run_command(f"systemctl stop {service}")
            st.warning("Остановлено")
            st.rerun()

    with col4:
        if st.button(
            "📊 Статус",
            key=f"status_{service}",
            use_container_width=True,
        ):
            st.code(
                run_command(
                    f"systemctl status {service} --no-pager"
                ),
                language="bash",
            )

    if st.button(
        f"📜 Показать последние логи: {title}",
        key=f"logs_{service}",
        use_container_width=True,
    ):
        st.code(
            run_command(
                f"journalctl -u {service} -n 120 --no-pager"
            ),
            language="bash",
        )

    st.divider()


st.subheader("Быстрые проверки")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button(
        "📁 Проверить видео",
        use_container_width=True,
    ):
        st.code(
            run_command(
                "ls -lh /opt/youtubefactory/output"
            ),
            language="bash",
        )

with col2:
    if st.button(
        "🎵 Проверить музыку",
        use_container_width=True,
    ):
        st.code(
            run_command(
                "find /opt/youtubefactory/library -type f "
                "\\( -name '*.mp3' -o -name '*.wav' -o -name '*.m4a' \\)"
            ),
            language="bash",
        )

with col3:
    if st.button(
        "🖼 Проверить изображения",
        use_container_width=True,
    ):
        st.code(
            run_command(
                "find /opt/youtubefactory/library -type f "
                "\\( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.webp' \\)"
            ),
            language="bash",
        )