from copy import deepcopy

from app.services.channel_library import (
    ChannelLibrary,
    WEEK_DAYS,
)


class VODScheduleService:

    def __init__(self, channel_name):

        self.channel_name = channel_name
        self.library = ChannelLibrary(
            channel_name
        )

    def get_config(self):
        return self.library.get_vod_config()

    def save_config(self, config):

        self._validate_config(config)
        self.library.save_vod_config(config)

        for day in WEEK_DAYS:
            item = config["weekly_schedule"][day]

            if (
                item.get("enabled")
                and item.get("profile_key")
            ):
                self.library.ensure_vod_profile(
                    item["profile_key"]
                )

        return config

    def update_day(self, day, values):

        if day not in WEEK_DAYS:
            raise ValueError(
                f"Неизвестный день недели: {day}"
            )

        config = self.get_config()
        current = deepcopy(
            config["weekly_schedule"][day]
        )
        current.update(values)

        config["weekly_schedule"][day] = current

        return self.save_config(config)

    def set_enabled(self, enabled):

        config = self.get_config()
        config["enabled"] = bool(enabled)

        return self.save_config(config)

    def _validate_config(self, config):

        if "weekly_schedule" not in config:
            raise ValueError(
                "В конфигурации отсутствует "
                "weekly_schedule."
            )

        for day in WEEK_DAYS:
            if day not in config["weekly_schedule"]:
                raise ValueError(
                    f"В расписании отсутствует день: "
                    f"{day}"
                )

            item = config["weekly_schedule"][day]

            minimum = int(
                item.get(
                    "min_duration_minutes",
                    60,
                )
            )
            maximum = int(
                item.get(
                    "max_duration_minutes",
                    120,
                )
            )

            if minimum < 60:
                raise ValueError(
                    f"{day}: минимальная длительность "
                    "не может быть меньше 60 минут."
                )

            if maximum > 120:
                raise ValueError(
                    f"{day}: максимальная длительность "
                    "не может быть больше 120 минут."
                )

            if maximum < minimum:
                raise ValueError(
                    f"{day}: максимальная длительность "
                    "меньше минимальной."
                )

            if item.get("enabled"):
                required = (
                    "genre",
                    "subgenre",
                    "profile_key",
                )

                for field in required:
                    if not str(
                        item.get(field, "")
                    ).strip():
                        raise ValueError(
                            f"{day}: не заполнено поле "
                            f"{field}."
                        )

                titles = item.get(
                    "title_templates",
                    [],
                )

                if not titles:
                    raise ValueError(
                        f"{day}: отсутствуют шаблоны "
                        "названий."
                    )

                if not str(
                    item.get(
                        "description_template",
                        "",
                    )
                ).strip():
                    raise ValueError(
                        f"{day}: отсутствует описание."
                    )
