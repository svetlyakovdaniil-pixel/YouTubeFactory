import streamlit as st

st.set_page_config(page_title="Источники изображений", page_icon="🖼️")

st.title("🖼️ Источники изображений")

st.divider()

if "image_providers" not in st.session_state:
    st.session_state.image_providers = []

with st.form("provider_form"):

    provider_name = st.text_input("Название")

    provider_type = st.selectbox(
        "Тип",
        [
            "NanoBanana",
            "Flux",
            "Google Images",
            "Локальная папка",
            "Другое",
        ],
    )

    prompt = st.text_area("Промпт по умолчанию")

    submit = st.form_submit_button("Добавить источник")

    if submit:

        st.session_state.image_providers.append(
            {
                "name": provider_name,
                "type": provider_type,
                "prompt": prompt,
            }
        )

        st.success("Источник добавлен")

st.divider()

st.subheader("Источники")

if not st.session_state.image_providers:

    st.info("Источников пока нет.")

else:

    for provider in st.session_state.image_providers:

        with st.container(border=True):

            st.write(f"### {provider['name']}")

            st.write(f"Тип: {provider['type']}")

            if provider["prompt"]:
                st.code(provider["prompt"])
