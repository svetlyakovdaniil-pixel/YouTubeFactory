import streamlit as st

from app.services.storage_service import StorageService

st.set_page_config(
    page_title="Тематики",
    page_icon="🎯",
)

storage = StorageService()

themes = storage.load("themes.json")

st.title("🎯 Тематики")

st.divider()

with st.form("theme_form"):

    name = st.text_input("Название")

    description = st.text_area("Описание")

    submit = st.form_submit_button("Добавить тематику")

    if submit:

        if name.strip():

            themes.append(
                {
                    "name": name.strip(),
                    "description": description.strip(),
                }
            )

            storage.save("themes.json", themes)

            st.success("Тематика добавлена")

            st.rerun()

st.divider()

st.subheader("Добавленные тематики")

if not themes:

    st.info("Тем пока нет.")

else:

    for index, theme in enumerate(themes):

        with st.container(border=True):

            col1, col2 = st.columns([6, 1])

            with col1:

                st.write(f"### {theme['name']}")

                st.write(theme["description"])

            with col2:

                if st.button(
                    "🗑️",
                    key=f"delete_theme_{index}",
                ):

                    themes.pop(index)

                    storage.save("themes.json", themes)

                    st.rerun()