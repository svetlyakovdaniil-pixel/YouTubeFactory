import streamlit as st
import json
from pathlib import Path

st.set_page_config(
    page_title="Добавить канал",
    page_icon="➕",
    layout="wide",
)

CONFIG = Path("/opt/youtubefactory/config/channels")
LIBRARY = Path("/opt/youtubefactory/library")

CONFIG.mkdir(parents=True, exist_ok=True)
LIBRARY.mkdir(parents=True, exist_ok=True)

st.title("➕ Добавить канал")

with st.form("channel"):

    name = st.text_input("Название канала")

    theme = st.text_input("Тематика")

    submit = st.form_submit_button("Создать")

if submit:

    if not name:

        st.error("Введите название.")

        st.stop()

    channel = {

        "name": name,

        "theme": theme,

        "music": {

            "provider": "",

            "style": ""

        },

        "images": {

            "provider": "",

            "prompt": ""

        }

    }

    with open(CONFIG / f"{name}.json", "w", encoding="utf8") as f:

        json.dump(channel, f, indent=4, ensure_ascii=False)

    root = LIBRARY / name

    (root / "images").mkdir(parents=True, exist_ok=True)

    (root / "music").mkdir(parents=True, exist_ok=True)

    (root / "videos").mkdir(parents=True, exist_ok=True)

    (root / "generated").mkdir(parents=True, exist_ok=True)

    (root / "finished").mkdir(parents=True, exist_ok=True)

    st.success("Канал создан.")

    st.rerun()