from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.channel_library import ChannelLibrary
from app.services.vod_planner import VODPlanner
from app.services.vod_publisher import VODPublisher
from app.video.vod_video_engine import VODVideoEngine


class VODJobService:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(channel_name)
        self.planner = VODPlanner(channel_name)
        self.engine = VODVideoEngine(channel_name)
        self.publisher = VODPublisher(channel_name)

    def _today_local_date(self, config):
        timezone_name = config.get(
            "timezone",
            "Asia/Almaty",
        )

        return datetime.now(
            ZoneInfo(timezone_name)
        ).date().isoformat()

    def already_published_today(
        self,
        local_date=None,
    ):
        config = self.library.get_vod_config()
        local_date = (
            local_date
            or self._today_local_date(config)
        )

        for item in reversed(
            self.library.get_vod_history()
        ):
            if (
                item.get("local_date")
                == local_date
                and item.get(
                    "youtube_video_id"
                )
            ):
                return item

        return None

    def run(
        self,
        duration_minutes=None,
        allow_short_test=False,
        force=False,
        privacy_override=None,
        delete_output_override=None,
    ):
        plan = self.planner.get_today_plan()

        if not plan.get("ready"):
            raise RuntimeError(
                "VOD-план не готов: "
                f"{plan.get('reason', '')}"
            )

        existing = (
            self.already_published_today(
                plan.get("local_date")
            )
        )

        if existing and not force:
            raise RuntimeError(
                "VOD на сегодня уже опубликован: "
                f"{existing.get('youtube_url', '')}"
            )

        if privacy_override:
            plan["privacy"] = (
                privacy_override
            )

        if (
            delete_output_override
            is not None
        ):
            plan[
                "delete_output_after_upload"
            ] = bool(
                delete_output_override
            )

        render_result = (
            self.engine.create_from_plan(
                plan=plan,
                duration_minutes=(
                    duration_minutes
                ),
                allow_short_test=(
                    allow_short_test
                ),
            )
        )

        try:
            publish_result = (
                self.publisher.publish(
                    plan=plan,
                    render_result=(
                        render_result
                    ),
                )
            )
        except Exception:
            # При ошибке загрузки MP4 остаётся
            # на сервере для повторной попытки.
            raise

        return {
            "plan": plan,
            "render_result": (
                render_result
            ),
            "publish_result": (
                publish_result
            ),
        }
