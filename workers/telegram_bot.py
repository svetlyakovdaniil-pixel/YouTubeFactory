import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from app.services.channel_library import ChannelLibrary
from app.services.channel_status import build_channel_status, service_name
from app.services.event_log import read_events
from app.services.error_advisor import format_advice
from app.services.recovery_manager import recover_channel, format_recovery_report
from app.services.preflight_manager import format_preflight_report


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"
CONFIG_PATH = PROJECT_ROOT / "config" / "telegram.json"
LOG_PATH = PROJECT_ROOT / "logs" / "telegram_bot.log"


def log(message):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def load_config():
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def api_request(method, payload=None):
    config = load_config()
    token = str(config.get("bot_token", "")).strip()

    if not token:
        raise RuntimeError("Telegram bot token is not configured")

    url = f"https://api.telegram.org/bot{token}/{method}"

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )

    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def allowed_chat(chat_id):
    config = load_config()
    expected = str(config.get("chat_id", "")).strip()
    return str(chat_id) == expected


def interface_url():
    config = load_config()
    return str(config.get("interface_url", "")).strip()


def list_channels():
    if not LIBRARY_ROOT.exists():
        return []

    channels = [
        path.name
        for path in LIBRARY_ROOT.iterdir()
        if path.is_dir()
    ]

    return sorted(channels)


def run_cmd(args):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
    )

    return result.returncode, result.stdout.strip(), result.stderr.strip()


def is_active(channel):
    code, stdout, stderr = run_cmd(
        ["systemctl", "is-active", service_name(channel)]
    )
    return stdout == "active"


def start_channel(channel):
    return run_cmd(["systemctl", "start", service_name(channel)])


def stop_channel(channel):
    return run_cmd(["systemctl", "stop", service_name(channel)])


def restart_channel(channel):
    return run_cmd(["systemctl", "restart", service_name(channel)])


def clear_channel_error(channel):
    library = ChannelLibrary(channel)
    state = library.get_state()

    state["paused"] = False
    state["last_error"] = ""
    state["running"] = False
    state["watch_url"] = ""
    state["started_at"] = ""
    state["current_track"] = ""
    state["track_index"] = 0

    library.save_state(state)


def channel_by_index(index):
    channels = list_channels()

    try:
        index = int(index)
    except Exception:
        return None

    if index < 0 or index >= len(channels):
        return None

    return channels[index]


def channel_index(channel):
    channels = list_channels()

    try:
        return channels.index(channel)
    except ValueError:
        return -1


def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    return api_request("sendMessage", payload)


def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "disable_web_page_preview": False,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    return api_request("editMessageText", payload)


def answer_callback(callback_query_id, text=""):
    return api_request(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": False,
        },
    )


def panel_button():
    url = interface_url()

    if not url:
        return None

    return {
        "text": "🌐 Открыть панель",
        "url": url,
    }


def main_keyboard():
    rows = [
        [
            {"text": "📊 Статус", "callback_data": "status"},
            {"text": "📺 Каналы", "callback_data": "channels"},
        ]
    ]

    panel = panel_button()
    if panel:
        rows.append([panel])

    return {"inline_keyboard": rows}


def channels_keyboard():
    channels = list_channels()
    rows = []

    for idx, channel in enumerate(channels):
        rows.append(
            [
                {
                    "text": channel,
                    "callback_data": f"ch:{idx}",
                }
            ]
        )

    rows.append(
        [
            {"text": "⬅ Назад", "callback_data": "menu"},
        ]
    )

    return {"inline_keyboard": rows}


def channel_keyboard(channel):
    idx = channel_index(channel)
    status = build_channel_status(
        channel,
        systemd_active=is_active(channel),
    )

    rows = []

    if status["effectively_running"]:
        rows.append(
            [
                {"text": "⏹ Остановить", "callback_data": f"confirm_stop:{idx}"},
                {"text": "🔄 Перезапустить", "callback_data": f"confirm_restart:{idx}"},
            ]
        )
    elif status["paused"]:
        rows.append(
            [
                {"text": "🔧 Восстановить", "callback_data": f"confirm_recover:{idx}"},
            ]
        )
    elif status["can_start"]:
        rows.append(
            [
                {"text": "▶ Запустить", "callback_data": f"start:{idx}"},
            ]
        )
    else:
        rows.append(
            [
                {"text": "🔍 Обновить", "callback_data": f"ch:{idx}"},
            ]
        )

    rows.append(
        [
            {"text": "📋 События", "callback_data": f"events:{idx}"},
            {"text": "🛡 Проверка", "callback_data": f"preflight:{idx}"},
        ]
    )

    rows.append(
        [
            {"text": "🔍 Обновить", "callback_data": f"ch:{idx}"},
        ]
    )

    rows.append(
        [
            {"text": "⬅ Каналы", "callback_data": "channels"},
        ]
    )

    panel = panel_button()
    if panel:
        rows.append([panel])

    return {"inline_keyboard": rows}


def confirm_keyboard(action, channel):
    idx = channel_index(channel)

    rows = [
        [
            {"text": "✅ Да", "callback_data": f"{action}:{idx}"},
            {"text": "❌ Нет", "callback_data": f"ch:{idx}"},
        ],
        [
            {"text": "⬅ Каналы", "callback_data": "channels"},
        ],
    ]

    panel = panel_button()
    if panel:
        rows.append([panel])

    return {"inline_keyboard": rows}


def format_status_line(channel):
    status = build_channel_status(
        channel,
        systemd_active=is_active(channel),
    )

    state = status["state"]

    if status["paused"]:
        headline = "🔴 Авария / требуется вмешательство"
    elif status["effectively_running"]:
        headline = "🟢 Эфир идёт"
    elif status["ready"]:
        headline = "🟡 Готов к запуску"
    else:
        headline = "⚫ Не готов"

    track = state.get("current_track") or "—"
    watch_url = state.get("watch_url") or ""

    text = (
        f"{headline}\n"
        f"Канал: {channel}\n"
        f"Музыка: {len(status['music_files'])}\n"
        f"Видео: {len(status['loop_videos'])}\n"
        f"Превью: {len(status['image_files'])}\n"
        f"YouTube: {'✅' if status['youtube_ready'] else '❌'}\n"
        f"Systemd: {'✅' if status['service_ok'] else '❌'}\n"
        f"Трек: {track}"
    )

    if status["missing"]:
        text += "\n\nНужно: " + ", ".join(status["missing"])

    if state.get("last_error"):
        text += "\n\n" + format_advice(state["last_error"])

    if watch_url:
        text += f"\n\nYouTube:\n{watch_url}"

    return text


def format_all_status():
    channels = list_channels()

    if not channels:
        return "Каналов пока нет."

    parts = ["📊 YouTube Factory\n"]

    for channel in channels:
        status = build_channel_status(
            channel,
            systemd_active=is_active(channel),
        )

        if status["paused"]:
            icon = "🛑"
            label = "требуется вмешательство"
        elif status["effectively_running"]:
            icon = "🟢"
            label = "эфир идёт"
        elif status["ready"]:
            icon = "🟡"
            label = "готов к запуску"
        else:
            icon = "⚫"
            label = "не готов"

        track = status["state"].get("current_track") or "—"

        parts.append(
            f"{icon} {channel}\n"
            f"{label}\n"
            f"Трек: {track}\n"
        )

    return "\n".join(parts)


def format_events(channel):
    events = read_events(channel, limit=8)

    if not events:
        return f"📋 {channel}\n\nСобытий пока нет."

    icons = {
        "success": "🟢",
        "info": "ℹ️",
        "warning": "🟡",
        "error": "🔴",
    }

    lines = [f"📋 Последние события\nКанал: {channel}\n"]

    for event in reversed(events):
        icon = icons.get(event.get("level"), "ℹ️")
        time_value = str(event.get("time", ""))[0:19].replace("T", " ")
        message = event.get("message", "")
        lines.append(f"{icon} {time_value}\n{message}")

        data = event.get("data", {}) or {}

        if data.get("error_title"):
            lines.append(
                f"Причина: {data.get('error_title')}\n"
                f"Что сделать: " + "; ".join(data.get("recommended_actions", [])[:3])
            )

        lines.append("")

    return "\n".join(lines)


def handle_command(chat_id, text):
    text = text.strip()

    if text in ["/start", "/help"]:
        send_message(
            chat_id,
            "🎛 YouTube Factory Bot\n\nВыбери действие:",
            reply_markup=main_keyboard(),
        )
        return

    if text == "/status":
        send_message(
            chat_id,
            format_all_status(),
            reply_markup=main_keyboard(),
        )
        return

    if text == "/channels":
        send_message(
            chat_id,
            "📺 Каналы:",
            reply_markup=channels_keyboard(),
        )
        return

    send_message(
        chat_id,
        "Не понял команду. Используй /status или /channels.",
        reply_markup=main_keyboard(),
    )


def handle_callback(callback):
    query_id = callback["id"]
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback.get("data", "")

    if not allowed_chat(chat_id):
        answer_callback(query_id, "Нет доступа")
        return

    answer_callback(query_id)

    if data == "menu":
        edit_message(
            chat_id,
            message_id,
            "🎛 YouTube Factory Bot\n\nВыбери действие:",
            reply_markup=main_keyboard(),
        )
        return

    if data == "status":
        edit_message(
            chat_id,
            message_id,
            format_all_status(),
            reply_markup=main_keyboard(),
        )
        return

    if data == "channels":
        edit_message(
            chat_id,
            message_id,
            "📺 Каналы:",
            reply_markup=channels_keyboard(),
        )
        return

    parts = data.split(":", 1)

    if len(parts) != 2:
        return

    action, index = parts
    channel = channel_by_index(index)

    if not channel:
        edit_message(
            chat_id,
            message_id,
            "Канал не найден.",
            reply_markup=main_keyboard(),
        )
        return

    if action == "ch":
        edit_message(
            chat_id,
            message_id,
            format_status_line(channel),
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "events":
        edit_message(
            chat_id,
            message_id,
            format_events(channel),
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "preflight":
        report, result = format_preflight_report(channel)

        edit_message(
            chat_id,
            message_id,
            report,
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "confirm_stop":
        edit_message(
            chat_id,
            message_id,
            f"⚠️ Остановить канал?\n\n{channel}",
            reply_markup=confirm_keyboard("stop", channel),
        )
        return

    if action == "confirm_restart":
        edit_message(
            chat_id,
            message_id,
            f"⚠️ Перезапустить канал?\n\n{channel}",
            reply_markup=confirm_keyboard("restart", channel),
        )
        return

    if action == "confirm_recover":
        edit_message(
            chat_id,
            message_id,
            f"⚠️ Сбросить аварию?\n\n{channel}",
            reply_markup=confirm_keyboard("recover", channel),
        )
        return

    if action == "start":
        status = build_channel_status(
            channel,
            systemd_active=is_active(channel),
        )

        if not status["can_start"]:
            result = "⚠️ Канал сейчас нельзя запустить."
        else:
            code, stdout, stderr = start_channel(channel)
            result = "✅ Команда запуска отправлена." if code == 0 else f"❌ Ошибка запуска:\n{stderr or stdout}"

        edit_message(
            chat_id,
            message_id,
            result + "\n\n" + format_status_line(channel),
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "stop":
        code, stdout, stderr = stop_channel(channel)
        result = "⏹ Канал остановлен." if code == 0 else f"❌ Ошибка остановки:\n{stderr or stdout}"
        edit_message(
            chat_id,
            message_id,
            result + "\n\n" + format_status_line(channel),
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "restart":
        code, stdout, stderr = restart_channel(channel)
        result = "🔄 Команда перезапуска отправлена." if code == 0 else f"❌ Ошибка перезапуска:\n{stderr or stdout}"
        edit_message(
            chat_id,
            message_id,
            result + "\n\n" + format_status_line(channel),
            reply_markup=channel_keyboard(channel),
        )
        return

    if action == "recover":
        recovery = recover_channel(channel)

        edit_message(
            chat_id,
            message_id,
            recovery["message"] + "\n\n" + format_status_line(channel),
            reply_markup=channel_keyboard(channel),
        )
        return


def run():
    log("Telegram bot started")

    offset = 0

    while True:
        try:
            config = load_config()

            if not config.get("enabled"):
                time.sleep(5)
                continue

            payload = {
                "timeout": 25,
                "offset": offset,
            }

            response = api_request("getUpdates", payload)

            for update in response.get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)

                if "message" in update:
                    message = update["message"]
                    chat_id = message.get("chat", {}).get("id")
                    text = message.get("text", "")

                    if not allowed_chat(chat_id):
                        continue

                    handle_command(chat_id, text)

                if "callback_query" in update:
                    handle_callback(update["callback_query"])

        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run()
