import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Library",
    page_icon="📚",
    layout="wide",
)

st.title("📚 Библиотека")

library = Path("/opt/youtubefactory/library")

channels = sorted(
    x.name
    for x in library.iterdir()
    if x.is_dir()
)

if not channels:
    st.warning("Нет каналов.")
    st.stop()

channel = st.selectbox(
    "Канал",
    channels,
)

folder = st.selectbox(
    "Папка",
    [
        "images",
        "videos",
        "music",
        "generated",
        "finished",
    ],
)

current = library / channel / folder

files = sorted(current.glob("*"))

search = st.text_input("🔍 Поиск").lower()

if search:
    files = [
        f for f in files
        if search in f.name.lower()
    ]

st.write(f"Файлов: {len(files)}")

cols = st.columns(4)

for index, file in enumerate(files):

    with cols[index % 4]:

        st.container(border=True)

        suffix = file.suffix.lower()

        if suffix in [
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        ]:

            st.image(
                str(file),
                use_container_width=True,
            )

        elif suffix in [
            ".mp4",
            ".mov",
            ".mkv",
        ]:

            st.video(str(file))

        elif suffix in [
            ".mp3",
            ".wav",
            ".ogg",
        ]:

            st.audio(str(file))

        st.caption(file.name)

        st.caption(
            f"{round(file.stat().st_size/1024/1024,2)} MB"
        )

        if st.button(
            "👁 Просмотр",
            key=f"view_{file}"
        ):
            st.session_state.preview = str(file)

        if st.button(
            "🗑 Удалить",
            key=f"delete_{file}"
        ):
            file.unlink()
            st.rerun()

if "preview" in st.session_state:

    st.divider()

    st.header("Просмотр")

    preview = Path(st.session_state.preview)

    suffix = preview.suffix.lower()

    if suffix in [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    ]:
        st.image(
            str(preview),
            use_container_width=True,
        )

    elif suffix in [
        ".mp4",
        ".mov",
        ".mkv",
    ]:
        st.video(str(preview))

    elif suffix in [
        ".mp3",
        ".wav",
        ".ogg",
    ]:
        st.audio(str(preview))

    if st.button("Закрыть просмотр"):
        del st.session_state.preview
        st.rerun()