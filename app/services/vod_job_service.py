from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.channel_library import ChannelLibrary
from app.services.vod_planner import VODPlanner
from app.services.vod_publisher import VODPublisher
from app.video.vod_video_engine import VODVideoEngine


class VODJobService:

    RESUMABLE_STAGES = {
        "ready",
        "uploading",
        "upload_error",
    }

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(channel_name)
        self.planner = VODPlanner(channel_name)
        self.engine = VODVideoEngine(channel_name)
        self.publisher = VODPublisher(channel_name)

    @staticmethod
    def _utc_now():
        return datetime.now(
            timezone.utc
        ).isoformat()

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

    def _save_state(self, **values):
        state = self.library.get_vod_state()
        state.update(values)
        state["updated_at"] = self._utc_now()

        self.library.save_vod_state(
            state
        )

        return state

    def _clear_stale_job(
        self,
        local_date,
    ):
        state = self.library.get_vod_state()

        state_local_date = str(
            state.get(
                "local_date",
                "",
            )
        ).strip()

        if (
            state_local_date
            and state_local_date
            != local_date
            and state.get("stage")
            != "published"
        ):
            self._save_state(
                running=False,
                stage="idle",
                local_date=local_date,
                plan=None,
                render_result=None,
                output_file="",
                manifest_file="",
                last_error="",
            )

    def _get_resumable_job(
        self,
        local_date,
    ):
        state = self.library.get_vod_state()

        if (
            state.get("local_date")
            != local_date
        ):
            return None

        if (
            state.get("stage")
            not in self.RESUMABLE_STAGES
        ):
            return None

        plan = state.get("plan")
        render_result = state.get(
            "render_result"
        )

        if not isinstance(plan, dict):
            return None

        if not isinstance(
            render_result,
            dict,
        ):
            return None

        output_path = Path(
            render_result.get(
                "output_path",
                "",
            )
        )
        manifest_path = Path(
            render_result.get(
                "manifest_path",
                "",
            )
        )

        if not output_path.is_file():
            return None

        if not manifest_path.is_file():
            return None

        if not isinstance(
            render_result.get("manifest"),
            dict,
        ):
            return None

        return {
            "plan": deepcopy(plan),
            "render_result": deepcopy(
                render_result
            ),
        }

    def _render(
        self,
        plan,
        duration_minutes,
        allow_short_test,
    ):
        local_date = plan["local_date"]

        self._save_state(
            running=True,
            stage="rendering",
            started_at=self._utc_now(),
            finished_at="",
            local_date=local_date,
            plan=deepcopy(plan),
            render_result=None,
            output_file="",
            manifest_file="",
            youtube_video_id="",
            youtube_url="",
            last_error="",
        )

        try:
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

        except Exception as error:
            self._save_state(
                running=False,
                stage="render_error",
                finished_at=self._utc_now(),
                last_error=str(error),
            )
            raise

        self._save_state(
            running=False,
            stage="ready",
            finished_at=self._utc_now(),
            plan=deepcopy(plan),
            render_result=deepcopy(
                render_result
            ),
            output_file=str(
                render_result.get(
                    "output_path",
                    "",
                )
            ),
            manifest_file=str(
                render_result.get(
                    "manifest_path",
                    "",
                )
            ),
            last_error="",
        )

        return render_result

    def run(
        self,
        duration_minutes=None,
        allow_short_test=False,
        force=False,
        privacy_override=None,
        delete_output_override=None,
    ):
        config = self.library.get_vod_config()
        local_date = self._today_local_date(
            config
        )

        self._clear_stale_job(
            local_date
        )

        existing = (
            self.already_published_today(
                local_date
            )
        )

        if existing and not force:
            raise RuntimeError(
                "VOD на сегодня уже опубликован: "
                f"{existing.get('youtube_url', '')}"
            )

        resumable = None

        if not force:
            resumable = (
                self._get_resumable_job(
                    local_date
                )
            )

        if resumable:
            plan = resumable["plan"]
            render_result = resumable[
                "render_result"
            ]

        else:
            plan = self.planner.get_today_plan()

            if not plan.get("ready"):
                raise RuntimeError(
                    "VOD-план не готов: "
                    f"{plan.get('reason', '')}"
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

            render_result = self._render(
                plan=plan,
                duration_minutes=(
                    duration_minutes
                ),
                allow_short_test=(
                    allow_short_test
                ),
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

        self._save_state(
            plan=deepcopy(plan),
            render_result=deepcopy(
                render_result
            ),
        )

        publish_result = (
            self.publisher.publish(
                plan=plan,
                render_result=render_result,
            )
        )

        return {
            "resumed": bool(resumable),
            "plan": plan,
            "render_result": render_result,
            "publish_result": publish_result,
        }