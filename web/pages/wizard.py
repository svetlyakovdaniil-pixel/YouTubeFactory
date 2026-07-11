from pathlib import Path
import yaml

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.pipeline import create_video


PROJECT_ROOT = Path(__file__).resolve().parents[2]

templates = Jinja2Templates(
    directory=PROJECT_ROOT / "web/templates"
)

router = APIRouter()


def load_channels():

    channels = []

    config_path = PROJECT_ROOT / "config/channels"

    if not config_path.exists():
        return channels

    for file in sorted(config_path.glob("*.yaml")):

        with open(file, "r", encoding="utf-8") as f:
            channels.append(yaml.safe_load(f))

    return channels


@router.get("/wizard")
def wizard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="wizard.html",
        context={
            "request": request,
            "channels": load_channels(),
        },
    )


@router.post("/wizard/create")
def create(channel: str = Form(...)):

    create_video(channel)

    return RedirectResponse("/wizard", status_code=303)