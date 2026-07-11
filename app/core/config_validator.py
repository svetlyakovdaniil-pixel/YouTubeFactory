REQUIRED_FIELDS = [
    "id",
    "name",
    "genre",
    "music",
    "video",
    "youtube",
]


def validate_channel(channel):

    missing = []

    for field in REQUIRED_FIELDS:
        if field not in channel:
            missing.append(field)

    if missing:
        raise ValueError(
            f"Channel '{channel.get('name', 'Unknown')}' is missing fields: {', '.join(missing)}"
        )