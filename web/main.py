from pathlib import Path
import yaml

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.pipeline import create_video
from web.pages.wizard import router as wizard_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(title="YouTube Factory")

templates = Jinja2Templates(directory=PROJECT_ROOT / "web/templates")

app.mount(
    "/static",
    StaticFiles(directory=PROJECT_ROOT / "web/static"),
    name="static",
)


VIDEO_STATUS = {
    "running": False,
    "channel": "",
    "message": "Ожидание"
}


def load_channels():

    channels = []

    config_path = PROJECT_ROOT / "config/channels"

    if not config_path.exists():
        return channels

    for file in sorted(config_path.glob("*.yaml")):

        with open(file, "r", encoding="utf-8") as f:
            channels.append(yaml.safe_load(f))

    return channels


def generate(channel: str):

    VIDEO_STATUS["running"] = True
    VIDEO_STATUS["channel"] = channel
    VIDEO_STATUS["message"] = "Создание видео..."

    try:
        create_video(channel)
        VIDEO_STATUS["message"] = "Видео успешно создано"

    except Exception as e:
        VIDEO_STATUS["message"] = str(e)

    VIDEO_STATUS["running"] = False


@app.get("/")
def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "title": "YouTube Factory",
            "channels": load_channels(),
            "status": VIDEO_STATUS,
        },
    )


@app.post("/generate/{channel}")
def generate_video(
    channel: str,
    background_tasks: BackgroundTasks,
):

    if not VIDEO_STATUS["running"]:
        background_tasks.add_task(generate, channel)

    return RedirectResponse("/", status_code=303)


app.include_router(wizard_router)