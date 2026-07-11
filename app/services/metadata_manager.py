import random

from app.services.channel_library import ChannelLibrary


DEFAULT_TITLES = {
    "Cosmic Slumber": [
        "🌙 Cosmic Slumber • Deep Sleep Music | Relaxing Space Ambient | 12 Hour Live",
        "😴 Deep Sleep Music LIVE • Calm Space Ambient | Cosmic Slumber",
        "🌌 Space Ambient for Sleeping • Relaxing Music LIVE | Cosmic Slumber",
        "💤 Sleep Music LIVE • Peaceful Ambient Sounds | Cosmic Slumber",
        "✨ Relaxing Ambient Music • Deep Sleep LIVE | Cosmic Slumber",
    ],
    "NoLyricsGroove": [
        "🎧 NoLyricsGroove • 90s Boom Bap Hip Hop Instrumentals | 12 Hour Live",
        "🔥 Old School Hip Hop Beats LIVE | NoLyricsGroove",
        "🎵 Boom Bap Instrumentals • 90s Hip Hop Radio LIVE",
        "🎤 Classic Hip Hop Beats • Instrumental Boom Bap LIVE",
        "🎧 Underground Boom Bap • Old School Instrumentals LIVE",
    ],
}


DEFAULT_DESCRIPTIONS = {
    "Cosmic Slumber": [
        """Welcome to Cosmic Slumber.

Relax with peaceful ambient music inspired by the silence of deep space. Perfect for sleep, meditation, stress relief, studying, reading, yoga, and relaxation.

Enjoy 12-hour continuous live streams featuring calming soundscapes, gentle atmospheric textures, and immersive space-inspired visuals.

Perfect for:
🌙 Sleeping
🧘 Meditation
📚 Studying
💻 Working
🌌 Relaxation
😌 Stress Relief

#sleepmusic #ambient #meditation #relaxingmusic #deepsleep #spaceambient""",
        """Escape into deep space with relaxing ambient music designed to help you sleep, focus, meditate, and unwind.

Cosmic Slumber streams peaceful atmospheric soundscapes inspired by the universe, stars, and endless galaxies.

Ideal for:
• Deep Sleep
• Meditation
• Focus
• Relaxation
• Stress Relief
• Background Ambient

Enjoy uninterrupted 12-hour live streams every day.

#sleep #ambientmusic #space #relaxation #meditation""",
        """Cosmic Slumber is a peaceful sleep music stream with calm ambient textures, soft space atmosphere, and relaxing soundscapes.

Use this stream for sleeping, meditation, reading, studying, yoga, deep focus, or simply relaxing after a long day.

No distractions. No harsh sounds. Just deep space ambience and gentle music for rest.

#deepsleepmusic #relaxingambient #sleepmusic #meditationmusic #spaceambient""",
    ],
    "NoLyricsGroove": [
        """Welcome to NoLyricsGroove.

Non-stop 90s-inspired boom bap and old school hip hop instrumentals with no vocals.

Perfect background music for:
🔥 Freestyle
✍️ Writing
📚 Studying
💻 Working
🎮 Gaming
🚗 Driving
🎧 Relaxing

Expect dusty drums, deep bass, vinyl textures, jazzy samples, and classic East Coast-inspired grooves.

12-hour live streams. No talking. No lyrics. Just beats.

#boombap #hiphopbeats #instrumental #90shiphop #beats #oldschoolhiphop""",
        """Classic 90s-inspired boom bap instrumentals streaming live.

No vocals.
No interruptions.
Just raw hip hop grooves.

Perfect for:
• Freestyle sessions
• Beat lovers
• Study
• Work
• Gaming
• Late night drives
• Creative focus

Inspired by the sound of the golden era of East Coast hip hop.

#boombap #instrumentalhiphop #oldschool #hiphopinstrumentals""",
        """NoLyricsGroove delivers instrumental hip hop with a 90s boom bap feel.

Expect dusty drums, deep basslines, jazzy loops, vinyl texture, underground energy, and old school groove.

Made for work, study, freestyle, gaming, driving, writing, and late-night focus.

No lyrics. No talking. Just instrumental hip hop.

#90shiphop #boombapbeats #instrumentalbeats #oldschoolhiphop #hiphopradio""",
    ],
}


def ensure_metadata_templates(channel_name):
    library = ChannelLibrary(channel_name)
    config = library.get_config()

    changed = False

    if not config.get("title_templates"):
        config["title_templates"] = DEFAULT_TITLES.get(
            channel_name,
            [
                f"{channel_name} LIVE | 12 Hour Stream",
                f"{channel_name} Radio LIVE",
            ],
        )
        changed = True

    if not config.get("description_templates"):
        config["description_templates"] = DEFAULT_DESCRIPTIONS.get(
            channel_name,
            [
                f"Welcome to {channel_name}. Enjoy this continuous live stream.",
            ],
        )
        changed = True

    if "last_title_template" not in config:
        config["last_title_template"] = ""
        changed = True

    if "last_description_template" not in config:
        config["last_description_template"] = ""
        changed = True

    if changed:
        library.save_config(config)

    return config


def pick_without_repeat(items, last_value):
    clean_items = [
        str(item).strip()
        for item in items
        if str(item).strip()
    ]

    if not clean_items:
        return ""

    if len(clean_items) == 1:
        return clean_items[0]

    candidates = [
        item
        for item in clean_items
        if item != last_value
    ]

    if not candidates:
        candidates = clean_items

    return random.choice(candidates)


def pick_stream_metadata(channel_name):
    library = ChannelLibrary(channel_name)
    config = ensure_metadata_templates(channel_name)

    title = pick_without_repeat(
        config.get("title_templates", []),
        config.get("last_title_template", ""),
    )

    description = pick_without_repeat(
        config.get("description_templates", []),
        config.get("last_description_template", ""),
    )

    if not title:
        title = config.get("title_template") or f"{channel_name} Radio"

    if not description:
        description = config.get("description", "")

    config["last_title_template"] = title
    config["last_description_template"] = description

    # Keep old fields in sync for visibility/backward compatibility.
    config["title_template"] = title
    config["description"] = description

    library.save_config(config)

    return {
        "title": title,
        "description": description,
    }


def templates_to_text(items):
    return "\n---\n".join([
        str(item).strip()
        for item in items
        if str(item).strip()
    ])


def text_to_templates(text):
    parts = str(text or "").split("\n---\n")

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]
