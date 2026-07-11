import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")
CONFIG_PATH = PROJECT_ROOT / "config" / "telegram.json"
EVENTS_LOG = PROJECT_ROOT / "logs" / "telegram_events.log"


class TelegramNotifier:

    def __init__(self):
        self.config = self.load_config()

    def load_config(self):
        if not CONFIG_PATH.exists():
            return {
                "enabled": False,
                "bot_token": "",
                "chat_id": "",
                "interface_url": "",
            }

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            return {
                "enabled": bool(data.get("enabled", False)),
                "bot_token": str(data.get("bot_token", "")).strip(),
                "chat_id": str(data.get("chat_id", "")).strip(),
                "interface_url": str(data.get("interface_url", "")).strip(),
            }

        except Exception:
            return {
                "enabled": False,
                "bot_token": "",
                "chat_id": "",
                "interface_url": "",
            }

    @staticmethod
    def save_config(enabled, bot_token, chat_id, interface_url=""):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "enabled": bool(enabled),
            "bot_token": str(bot_token).strip(),
            "chat_id": str(chat_id).strip(),
            "interface_url": str(interface_url).strip(),
        }

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return data

    def is_configured(self):
        return (
            bool(self.config.get("enabled"))
            and bool(self.config.get("bot_token"))
            and bool(self.config.get("chat_id"))
        )

    def log_event(self, level, channel, message):
        EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "channel": channel,
                "message": message,
            },
            ensure_ascii=False,
        )

        with open(EVENTS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def with_interface_url(self, text):
        interface_url = str(self.config.get("interface_url", "")).strip()

        if not interface_url:
            return text

        return text + f"\n\n🔗 Панель управления:\n{interface_url}"

    def send(self, text, channel="", level="info"):
        text = self.with_interface_url(text)

        self.log_event(
            level=level,
            channel=channel,
            message=text,
        )

        if not self.is_configured():
            return {
                "ok": False,
                "error": "Telegram is not configured",
            }

        token = self.config["bot_token"]
        chat_id = self.config["chat_id"]

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "false",
            }
        ).encode("utf-8")

        try:
            request = urllib.request.Request(
                url,
                data=payload,
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")

            return {
                "ok": True,
                "response": body,
            }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }


def notify_info(channel, message):
    notifier = TelegramNotifier()

    return notifier.send(
        text=f"🟢 YouTube Factory\n\nКанал: {channel}\n\n{message}",
        channel=channel,
        level="info",
    )


def notify_warning(channel, message):
    notifier = TelegramNotifier()

    return notifier.send(
        text=f"🟡 YouTube Factory\n\nКанал: {channel}\n\n{message}",
        channel=channel,
        level="warning",
    )


def notify_error(channel, message):
    notifier = TelegramNotifier()

    return notifier.send(
        text=f"🔴 YouTube Factory\n\nКанал: {channel}\n\n{message}",
        channel=channel,
        level="error",
    )
