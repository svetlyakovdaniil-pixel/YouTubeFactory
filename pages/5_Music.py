import streamlit as st

st.set_page_config(page_title="Музыка", page_icon="🎵")

st.title("🎵 Источники музыки")

st.divider()

if "music_sources" not in st.session_state:
    st.session_state.music_sources = []

with st.form("music_form"):

    name = st.text_input("Название")

    provider = st.selectbox(
        "Источник",
        [
            "Suno",
            "YouTube Audio Library",
            "Локальная папка",
            "Другое",
        ],
    )

    style = st.text_input("Стиль музыки")

    prompt = st.text_area("Промпт")

    submit = st.form_submit_button("Добавить")

    if submit:

        st.session_state.music_sources.append(
            {
                "name": name,
                "provider": provider,
                "style": style,
                "prompt": prompt,
            }
        )

        st.success("Источник музыки добавлен")

st.divider()

st.subheader("Добавленные источники")

if not st.session_state.music_sources:

    st.info("Источников музыки пока нет.")

else:

    for music in st.session_state.music_sources:

        with st.container(border=True):

            st.write(f"### {music['name']}")

            st.write(f"Источник: {music['provider']}")

            st.write(f"Стиль: {music['style']}")

            if music["prompt"]:
                st.code(music["prompt"])
