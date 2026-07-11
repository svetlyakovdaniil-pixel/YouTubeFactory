import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]


PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"


class ChannelAuth:

    DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, channel_name):

        self.channel_name = channel_name

        self.youtube_dir = (
            LIBRARY_ROOT
            / channel_name
            / "youtube"
        )

        self.youtube_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.client_secret = (
            self.youtube_dir
            / "client_secret.json"
        )

        self.token = (
            self.youtube_dir
            / "token.json"
        )

        self.device_auth = (
            self.youtube_dir
            / "device_auth.json"
        )

    def is_connected(self):

        return (
            self.client_secret.exists()
            and self.token.exists()
        )

    def has_client_secret(self):

        return self.client_secret.exists()

    def has_token(self):

        return self.token.exists()

    def _load_client_config(self):

        if not self.client_secret.exists():
            raise FileNotFoundError(
                f"Не найден файл:\n{self.client_secret}"
            )

        with open(self.client_secret, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = data.get("installed") or data.get("web")

        if not config:
            raise ValueError(
                "Некорректный client_secret.json. "
                "Нужен OAuth Client ID типа Desktop app."
            )

        client_id = config.get("client_id")
        client_secret = config.get("client_secret")

        if not client_id or not client_secret:
            raise ValueError(
                "В client_secret.json не найден client_id или client_secret."
            )

        return {
            "client_id": client_id,
            "client_secret": client_secret,
        }

    def start_device_flow(self):

        config = self._load_client_config()

        payload = urllib.parse.urlencode(
            {
                "client_id": config["client_id"],
                "scope": " ".join(SCOPES),
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            self.DEVICE_CODE_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

        device_data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "device_code": result["device_code"],
            "user_code": result["user_code"],
            "verification_url": result.get(
                "verification_url",
                "https://www.google.com/device",
            ),
            "verification_url_complete": result.get(
                "verification_url_complete",
                "",
            ),
            "expires_in": result.get("expires_in", 1800),
            "interval": result.get("interval", 5),
            "created_at": int(time.time()),
        }

        self.device_auth.write_text(
            json.dumps(
                device_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return device_data

    def get_pending_device_flow(self):

        if not self.device_auth.exists():
            return None

        with open(self.device_auth, "r", encoding="utf-8") as f:
            data = json.load(f)

        created_at = int(data.get("created_at", 0))
        expires_in = int(data.get("expires_in", 0))

        if created_at + expires_in < int(time.time()):
            self.device_auth.unlink(missing_ok=True)
            return None

        return data

    def finish_device_flow(self):

        data = self.get_pending_device_flow()

        if not data:
            raise RuntimeError(
                "Код авторизации не найден или устарел. "
                "Нажмите «Получить код подключения» ещё раз."
            )

        payload = urllib.parse.urlencode(
            {
                "client_id": data["client_id"],
                "client_secret": data["client_secret"],
                "device_code": data["device_code"],
                "grant_type": (
                    "urn:ietf:params:oauth:grant-type:device_code"
                ),
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            self.TOKEN_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                token_response = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")

            try:
                error_data = json.loads(error_body)
            except Exception:
                error_data = {}

            error = error_data.get("error", "")

            if error == "authorization_pending":
                return {
                    "ok": False,
                    "pending": True,
                    "message": (
                        "Авторизация ещё не завершена. "
                        "Откройте ссылку Google, введите код и нажмите "
                        "проверку ещё раз."
                    ),
                }

            if error == "slow_down":
                return {
                    "ok": False,
                    "pending": True,
                    "message": (
                        "Google просит подождать несколько секунд. "
                        "Попробуйте проверить ещё раз чуть позже."
                    ),
                }

            if error == "expired_token":
                self.device_auth.unlink(missing_ok=True)

                return {
                    "ok": False,
                    "pending": False,
                    "message": (
                        "Код устарел. Нажмите «Получить код подключения» "
                        "ещё раз."
                    ),
                }

            raise RuntimeError(
                error_data.get(
                    "error_description",
                    error_body,
                )
            )

        refresh_token = token_response.get("refresh_token")

        if not refresh_token:
            raise RuntimeError(
                "Google не вернул refresh_token. "
                "Нажмите «Переподключить», затем создайте код заново "
                "и пройдите авторизацию ещё раз."
            )

        token_data = {
            "token": token_response.get("access_token"),
            "refresh_token": refresh_token,
            "token_uri": self.TOKEN_URL,
            "client_id": data["client_id"],
            "client_secret": data["client_secret"],
            "scopes": SCOPES,
        }

        self.token.write_text(
            json.dumps(
                token_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.device_auth.unlink(missing_ok=True)

        return {
            "ok": True,
            "pending": False,
            "message": "YouTube успешно подключён.",
        }

    def connect(self):

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secret),
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=8765,
            open_browser=False,
        )

        self.token.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    def disconnect(self):

        if self.token.exists():
            self.token.unlink()

        if self.device_auth.exists():
            self.device_auth.unlink()

    def copy_client_secret(self, source):

        Path(source).replace(self.client_secret)
