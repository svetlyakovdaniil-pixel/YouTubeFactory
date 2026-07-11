from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]

PROJECT_ROOT = Path("/opt/youtubefactory")
LIBRARY_ROOT = PROJECT_ROOT / "library"

def _youtube_dir(channel_name):
    path = LIBRARY_ROOT / channel_name / "youtube"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_credentials(channel_name):
    youtube_dir = _youtube_dir(channel_name)
    client_secret = youtube_dir / "client_secret.json"
    token = youtube_dir / "token.json"

    if not client_secret.exists():
        raise FileNotFoundError(f"Не найден файл client_secret.json:\n{client_secret}")

    credentials = None

    if token.exists():
        credentials = Credentials.from_authorized_user_file(str(token), SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    if credentials and credentials.valid:
        return credentials

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    credentials = flow.run_local_server(port=8765, open_browser=False)

    token.write_text(credentials.to_json(), encoding="utf-8")
    return credentials

def get_youtube_service(channel_name):
    return build("youtube", "v3", credentials=get_credentials(channel_name))
