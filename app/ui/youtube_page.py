from pathlib import Path

import streamlit as st

from app.youtube.channel_auth import ChannelAuth


LIBRARY_ROOT = Path("/opt/youtubefactory/library")


def _save_uploaded_client_secret(channel_name, uploaded_file, client_secret_path):
    state_key = f"saved_client_secret_{channel_name}"

    uploaded_signature = (
        uploaded_file.name,
        uploaded_file.size,
    )

    if st.session_state.get(state_key) == uploaded_signature:
        return False

    client_secret_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(client_secret_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.session_state[state_key] = uploaded_signature

    return True


def _status_icon(done):
    return "✅" if done else "⬜"


def _render_oauth_instruction():
    with st.expander("❓ Как получить client_secret.json", expanded=False):
        st.markdown(
            """
            ### 1. Откройте Google Cloud

            Перейдите в **Google Cloud Console**.

            ### 2. Выберите проект

            Используйте уже созданный проект:

            `YouTube Factory`

            Новый Google Cloud Project для каждого канала создавать не нужно.

            ### 3. Откройте раздел

            `APIs & Services → Credentials`

            ### 4. Создайте OAuth Client

            Нажмите:

            `Create credentials → OAuth client ID`

            ### 5. Выберите тип приложения

            Для текущей схемы подключения выберите:

            `TVs and Limited Input devices`

            ### 6. Назовите OAuth Client

            Лучше назвать по имени канала, например:

            `NoLyricsGroove`

            ### 7. Скачайте JSON

            После создания нажмите **Download JSON**.

            Полученный файл загрузите ниже как `client_secret.json`.
            """
        )


def _render_connected_state(auth, channel_name, client_secret, token):
    st.success("🟢 YouTube подключен")

    st.write("**Статус подключения**")
    st.write(f"Client Secret: {'✅' if client_secret.exists() else '❌'}")
    st.write(f"Token: {'✅' if token.exists() else '❌'}")

    st.divider()

    st.write("**Готово**")
    st.info(
        f"Канал **{channel_name}** уже подключен к YouTube. "
        "Можно загружать музыку, видео и запускать эфир."
    )

    st.divider()

    with st.expander("♻ Переподключить YouTube"):
        st.warning(
            "Переподключение удалит текущий token.json. "
            "После этого нужно будет снова пройти авторизацию Google."
        )

        confirm = st.text_input(
            f"Чтобы переподключить, напишите название канала: {channel_name}",
            key=f"youtube_reconnect_confirm_{channel_name}",
        )

        if st.button(
            "♻ Подтвердить переподключение",
            use_container_width=True,
            disabled=confirm != channel_name,
            key=f"youtube_reconnect_button_{channel_name}",
        ):
            try:
                auth.disconnect()
                st.success("Подключение сброшено. Теперь подключите YouTube заново.")
                st.rerun()

            except Exception as e:
                st.error(str(e))


def _render_not_connected_state(auth, channel_name, client_secret, token):
    client_secret_exists = client_secret.exists()
    token_exists = token.exists()
    pending = auth.get_pending_device_flow()

    completed_steps = 0

    if client_secret_exists:
        completed_steps += 1

    if pending:
        completed_steps += 1

    if token_exists:
        completed_steps = 5

    progress = completed_steps / 5

    st.warning("🟡 YouTube не подключен")

    st.write("**Мастер подключения**")
    st.progress(progress)
    st.caption(f"Готовность подключения: {int(progress * 100)}%")

    st.markdown(
        f"""
        {_status_icon(client_secret_exists)} **Шаг 1. Создать OAuth Client в Google Cloud**  
        {_status_icon(client_secret_exists)} **Шаг 2. Загрузить client_secret.json**  
        {_status_icon(pending is not None)} **Шаг 3. Получить код подключения**  
        {_status_icon(pending is not None)} **Шаг 4. Авторизоваться в Google**  
        {_status_icon(token_exists)} **Шаг 5. Проверить подключение**
        """
    )

    _render_oauth_instruction()

    st.divider()

    st.subheader("Шаг 2. Загрузить client_secret.json")

    st.write(f"Client Secret: {'✅' if client_secret_exists else '❌'}")
    st.write(f"Token: {'✅' if token_exists else '❌'}")

    uploaded = st.file_uploader(
        "Загрузить client_secret.json",
        type=["json"],
        key=f"client_secret_{channel_name}",
    )

    if uploaded is not None:
        try:
            saved = _save_uploaded_client_secret(
                channel_name,
                uploaded,
                client_secret,
            )

            if saved:
                st.success(
                    "client_secret.json сохранён. "
                    "Теперь переходите к получению кода подключения."
                )
                client_secret_exists = True
            else:
                st.info("client_secret.json уже загружен.")

        except Exception as e:
            st.error(f"Не удалось сохранить client_secret.json: {e}")

    st.divider()

    st.subheader("Шаг 3. Получить код подключения")

    if not client_secret.exists():
        st.info("Сначала загрузите client_secret.json.")
        return

    col_code, col_check = st.columns(2)

    with col_code:
        if st.button(
            "🔑 Получить код подключения",
            use_container_width=True,
            key=f"youtube_get_code_{channel_name}",
        ):
            try:
                pending = auth.start_device_flow()
                st.success("Код подключения создан.")
                st.rerun()

            except Exception as e:
                st.error(str(e))
                st.warning(
                    "Проверьте, что OAuth Client создан с типом "
                    "TVs and Limited Input devices."
                )

    with col_check:
        if st.button(
            "✅ Проверить подключение",
            use_container_width=True,
            disabled=pending is None,
            key=f"youtube_check_{channel_name}",
        ):
            try:
                result = auth.finish_device_flow()

                if result.get("ok"):
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.warning(result["message"])

            except Exception as e:
                st.error(str(e))

    pending = auth.get_pending_device_flow()

    if pending:
        st.divider()

        st.subheader("Шаг 4. Авторизоваться в Google")

        verification_url = pending.get(
            "verification_url",
            "https://www.google.com/device",
        )

        verification_url_complete = pending.get(
            "verification_url_complete",
            "",
        )

        user_code = pending.get("user_code", "")

        link_url = verification_url_complete or verification_url

        st.link_button(
            "🌐 Открыть страницу авторизации Google",
            link_url,
            use_container_width=True,
        )

        st.write("**Код подключения:**")
        st.code(user_code)

        st.info(
            "Откройте страницу Google, введите код выше, выберите нужный "
            "Google/YouTube-аккаунт, разрешите доступ, затем вернитесь сюда "
            "и нажмите «Проверить подключение»."
        )

        st.caption(
            "Если код устарел, нажмите «Получить код подключения» ещё раз."
        )


def render(channel_name):
    auth = ChannelAuth(channel_name)

    st.subheader("YouTube")

    youtube_dir = LIBRARY_ROOT / channel_name / "youtube"
    client_secret = youtube_dir / "client_secret.json"
    token = youtube_dir / "token.json"

    if client_secret.exists() and token.exists():
        _render_connected_state(
            auth=auth,
            channel_name=channel_name,
            client_secret=client_secret,
            token=token,
        )
    else:
        _render_not_connected_state(
            auth=auth,
            channel_name=channel_name,
            client_secret=client_secret,
            token=token,
        )
