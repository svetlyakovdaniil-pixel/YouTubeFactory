from pathlib import Path

import streamlit as st

from app.services.track_library import (
    GENRES,
    MOODS,
    SUBGENRES_BY_GENRE,
    TrackLibrary,
)


st.set_page_config(
    page_title="Музыка",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 Библиотека музыки")

library_root = Path("/opt/youtubefactory/library")

channels = sorted(
    item.name
    for item in library_root.iterdir()
    if item.is_dir()
)

if not channels:
    st.warning("Нет каналов.")
    st.stop()

channel = st.selectbox(
    "Канал",
    channels,
)

track_library = TrackLibrary(channel)

st.divider()
st.subheader("Загрузка треков")

genre = st.selectbox(
    "Жанр",
    GENRES,
)

subgenre = st.selectbox(
    "Поджанр",
    SUBGENRES_BY_GENRE[genre],
)

mood = st.selectbox(
    "Настроение",
    MOODS,
)

col_artist, col_bpm = st.columns(2)

with col_artist:
    artist = st.text_input(
        "Исполнитель",
        value="",
        help="Необязательно. Можно оставить пустым.",
    )

with col_bpm:
    bpm = st.number_input(
        "BPM",
        min_value=0,
        max_value=300,
        value=0,
        step=1,
        help="0 — не указывать BPM.",
    )

uploaded_files = st.file_uploader(
    "Выбери один или несколько треков",
    type=["mp3", "wav", "m4a", "aac", "flac"],
    accept_multiple_files=True,
)

if st.button(
    "Загрузить треки",
    type="primary",
    use_container_width=True,
    disabled=not uploaded_files,
):
    results = track_library.upload_tracks(
        uploaded_files=uploaded_files,
        genre=genre,
        subgenre=subgenre,
        mood=mood,
        artist=artist,
        bpm=bpm or None,
    )

    uploaded_count = sum(
        1
        for item in results
        if item.get("ok") and not item.get("duplicate")
    )
    duplicate_count = sum(
        1
        for item in results
        if item.get("duplicate")
    )
    error_items = [
        item
        for item in results
        if not item.get("ok")
    ]

    if uploaded_count:
        st.success(
            f"Загружено треков: {uploaded_count}"
        )

    if duplicate_count:
        st.warning(
            f"Пропущено дубликатов: {duplicate_count}"
        )

    for item in error_items:
        st.error(
            f"{item['filename']}: {item['error']}"
        )

    if uploaded_count:
        st.rerun()

st.divider()
st.subheader("Треки канала")

tracks = track_library.list_tracks()

if not tracks:
    st.info("На этом канале пока нет треков.")
    st.stop()

st.caption(
    f"Всего треков: {len(tracks)}"
)

for index, item in enumerate(tracks):
    audio_path = item["audio_path"]
    metadata = item["metadata"]

    title = metadata.get("title") or audio_path.stem
    subgenre_value = metadata.get("subgenre") or "Без поджанра"
    mood_value = metadata.get("mood") or "Без настроения"

    with st.expander(
        f"{title} · {subgenre_value} · {mood_value}"
    ):
        st.audio(str(audio_path))

        col1, col2, col3 = st.columns(3)

        with col1:
            edit_genre = st.selectbox(
                "Жанр",
                GENRES,
                index=(
                    GENRES.index(metadata["genre"])
                    if metadata.get("genre") in GENRES
                    else 0
                ),
                key=f"genre_{channel}_{index}",
            )

        available_subgenres = SUBGENRES_BY_GENRE[
            edit_genre
        ]

        with col2:
            edit_subgenre = st.selectbox(
                "Поджанр",
                available_subgenres,
                index=(
                    available_subgenres.index(
                        metadata["subgenre"]
                    )
                    if metadata.get("subgenre")
                    in available_subgenres
                    else 0
                ),
                key=f"subgenre_{channel}_{index}",
            )

        with col3:
            edit_mood = st.selectbox(
                "Настроение",
                MOODS,
                index=(
                    MOODS.index(metadata["mood"])
                    if metadata.get("mood") in MOODS
                    else 0
                ),
                key=f"mood_{channel}_{index}",
            )

        col4, col5, col6 = st.columns(3)

        with col4:
            edit_title = st.text_input(
                "Название трека",
                value=title,
                key=f"title_{channel}_{index}",
            )

        with col5:
            edit_artist = st.text_input(
                "Исполнитель",
                value=metadata.get("artist", ""),
                key=f"artist_{channel}_{index}",
            )

        with col6:
            edit_bpm = st.number_input(
                "BPM",
                min_value=0,
                max_value=300,
                value=int(metadata.get("bpm") or 0),
                step=1,
                key=f"bpm_{channel}_{index}",
            )

        live_enabled = st.checkbox(
            "Использовать в LIVE",
            value=bool(
                metadata.get("live_enabled", True)
            ),
            key=f"live_{channel}_{index}",
        )

        vod_enabled = st.checkbox(
            "Использовать в VOD",
            value=bool(
                metadata.get("vod_enabled", True)
            ),
            key=f"vod_{channel}_{index}",
        )

        save_col, delete_col = st.columns(2)

        with save_col:
            if st.button(
                "Сохранить метаданные",
                use_container_width=True,
                key=f"save_{channel}_{index}",
            ):
                track_library.save_metadata(
                    audio_path,
                    {
                        "title": edit_title.strip()
                        or audio_path.stem,
                        "artist": edit_artist.strip(),
                        "genre": edit_genre,
                        "subgenre": edit_subgenre,
                        "mood": edit_mood,
                        "bpm": edit_bpm or None,
                        "live_enabled": live_enabled,
                        "vod_enabled": vod_enabled,
                    },
                )
                st.success("Метаданные сохранены.")
                st.rerun()

        with delete_col:
            if st.button(
                "Удалить трек",
                use_container_width=True,
                key=f"delete_{channel}_{index}",
            ):
                track_library.delete_track(
                    audio_path
                )
                st.success("Трек удалён.")
                st.rerun()
