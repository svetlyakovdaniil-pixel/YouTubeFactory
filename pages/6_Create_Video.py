import streamlit as st
from pathlib import Path

from app.pipeline import create_video

st.set_page_config(
    page_title="Create Video",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 Создание видео")

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

duration = st.selectbox(
    "Длительность",
    [
        "10 минут",
        "30 минут",
        "1 час",
        "3 часа",
        "6 часов",
        "12 часов",
    ],
)

if st.button(
    "Создать видео",
    use_container_width=True,
):

    with st.spinner("Создание видео..."):

        result = create_video(channel)

    st.success("Видео создано.")

    st.video(str(result))