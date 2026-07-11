import streamlit as st
from pathlib import Path
import shutil
import uuid

st.set_page_config(
    page_title="Generation",
    page_icon="✨",
    layout="wide",
)

st.title("✨ Генерация контента")

library = Path("/opt/youtubefactory/library")

channels = sorted([x.name for x in library.iterdir() if x.is_dir()])

if not channels:
    st.warning("Нет каналов.")
    st.stop()

channel = st.selectbox("Канал", channels)

content_type = st.radio(
    "Тип контента",
    [
        "Изображение",
        "Музыка"
    ],
    horizontal=True
)

provider = st.selectbox(
    "Провайдер",
    [
        "NanoBanana",
        "Suno"
    ]
)

prompt = st.text_area(
    "Промпт",
    height=180
)

st.divider()

st.subheader("Пока используется тестовая загрузка")

uploaded = st.file_uploader(
    "Выберите готовый файл",
    type=None
)

if st.button("Добавить в библиотеку", use_container_width=True):

    if uploaded is None:
        st.error("Выберите файл.")
        st.stop()

    extension = Path(uploaded.name).suffix

    filename = f"{uuid.uuid4()}{extension}"

    if content_type == "Изображение":
        target = (
            library
            / channel
            / "images"
            / filename
        )
    else:
        target = (
            library
            / channel
            / "music"
            / filename
        )

    with open(target, "wb") as f:
        shutil.copyfileobj(uploaded, f)

    st.success("Файл успешно добавлен.")