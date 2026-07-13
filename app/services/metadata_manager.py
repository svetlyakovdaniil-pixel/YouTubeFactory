import random
from copy import deepcopy

from app.services.channel_library import ChannelLibrary


RECENT_HISTORY_LIMIT = 20
GENERATION_ATTEMPTS = 100


CHANNEL_PROFILES = {
    "Cosmic Slumber": {
        "title_patterns": [
            "{icon} {subject} • {mood} | {purpose} LIVE",
            "{icon} {purpose} • {subject} | {duration} Live",
            "{icon} {mood} {subject} for {use_case} • LIVE",
            "{icon} {subject} Radio • {purpose} | Cosmic Slumber",
            "{icon} Cosmic Slumber • {mood} {subject} | LIVE",
            "{icon} {use_case} with {subject} • {duration} Stream",
            "{icon} {subject} • Music for {use_case} | LIVE",
            "{icon} {mood} Space Music • {purpose} | Cosmic Slumber",
        ],
        "icons": [
            "🌌",
            "🌙",
            "✨",
            "🪐",
            "💫",
        ],
        "subjects": [
            "Deep Space Ambient",
            "Cosmic Sleep Music",
            "Space Ambient Music",
            "Interstellar Soundscapes",
            "Celestial Ambient",
            "Dreamy Space Music",
            "Galaxy Sleep Sounds",
            "Atmospheric Space Music",
            "Deep Cosmos Ambience",
            "Ethereal Space Ambient",
        ],
        "moods": [
            "Peaceful",
            "Calm",
            "Relaxing",
            "Soothing",
            "Gentle",
            "Dreamy",
            "Serene",
            "Tranquil",
            "Soft",
            "Immersive",
        ],
        "purposes": [
            "Deep Sleep & Relaxation",
            "Sleep, Meditation & Focus",
            "Calm Night and Rest",
            "Stress Relief & Meditation",
            "Peaceful Sleep",
            "Relaxation and Deep Focus",
            "Nighttime Relaxation",
            "Sleep and Inner Peace",
        ],
        "use_cases": [
            "Deep Sleep",
            "Sleeping and Meditation",
            "Relaxation",
            "Nighttime Rest",
            "Study and Focus",
            "Stress Relief",
            "Reading and Sleep",
            "Yoga and Meditation",
        ],
        "durations": [
            "12 Hour",
            "All Night",
            "Long-Form",
            "Continuous",
        ],
        "description_openers": [
            "Welcome to Cosmic Slumber, a peaceful journey through deep space and relaxing ambient sound.",
            "Drift into the quiet of the universe with calming space-inspired music from Cosmic Slumber.",
            "Slow down, breathe deeply, and relax with gentle cosmic ambience designed for rest.",
            "Explore distant galaxies through soft atmospheric music created for sleep and relaxation.",
            "Let peaceful space soundscapes carry you into deep sleep, meditation, or focused work.",
            "Cosmic Slumber brings calm celestial textures and immersive ambient music to your night.",
        ],
        "description_middles": [
            "This continuous stream is suitable for sleeping, meditation, reading, studying, yoga, stress relief, and quiet background listening.",
            "Use this music while resting, working, meditating, reading, or creating a calm atmosphere before sleep.",
            "Soft textures, slow movement, and spacious sound create an uninterrupted background for relaxation and deep focus.",
            "There are no sudden interruptions or harsh sounds—only gentle ambient layers inspired by stars, planets, and distant galaxies.",
            "The stream is designed to remain subtle and unobtrusive while helping you unwind, concentrate, or fall asleep.",
            "Enjoy a long-form soundscape for peaceful nights, meditation sessions, creative focus, and recovery after a busy day.",
        ],
        "description_closers": [
            "Subscribe to Cosmic Slumber for new space ambience, sleep music, and relaxing live sessions.",
            "Return whenever you need a quiet place to sleep, focus, breathe, and reset.",
            "New cosmic soundscapes and long ambient sessions are added regularly.",
            "Keep the volume comfortable, dim the lights, and enjoy your journey through deep space.",
        ],
        "hashtags": [
            "#sleepmusic #spaceambient #ambientmusic #deepsleep #relaxingmusic",
            "#cosmicambient #meditationmusic #sleep #relaxation #space",
            "#deepsleepmusic #ambient #meditation #focusmusic #cosmicslumber",
            "#spaceambient #calmmusic #sleepmusic #stressrelief #relax",
        ],
    },
    "NoLyricsGroove": {
        "title_patterns": [
            "{icon} {subject} • {mood} | {purpose} LIVE",
            "{icon} {mood} {subject} • {duration} Radio",
            "{icon} {subject} for {use_case} | NoLyricsGroove LIVE",
            "{icon} NoLyricsGroove • {subject} | {purpose}",
            "{icon} {series} • {subject} | LIVE",
            "{icon} {subject} Radio • {series} | No Vocals",
            "{icon} {mood} Instrumentals • {purpose} | LIVE",
            "{icon} {series}: {subject} • {duration} Stream",
        ],
        "icons": [
            "🎧",
            "📼",
            "💿",
            "🔥",
            "🎵",
        ],
        "subjects": [
            "90s Boom Bap Instrumentals",
            "Old School Hip Hop Beats",
            "Underground Boom Bap",
            "Golden Era Hip Hop Beats",
            "Dusty Hip Hop Instrumentals",
            "East Coast Instrumentals",
            "Classic Boom Bap Beats",
            "Raw Instrumental Hip Hop",
            "Vinyl Hip Hop Beats",
            "Jazzy Boom Bap Instrumentals",
        ],
        "moods": [
            "Raw",
            "Classic",
            "Dusty",
            "Underground",
            "Late Night",
            "Golden Era",
            "Hard-Hitting",
            "Vinyl-Infused",
            "Jazzy",
            "Timeless",
        ],
        "purposes": [
            "Study, Work & Freestyle",
            "Beats for Focus and Writing",
            "No Vocals, Just Beats",
            "Freestyle and Creative Focus",
            "Work, Gaming and Late Drives",
            "Writing and Deep Focus",
            "Non-Stop Instrumental Hip Hop",
            "Focus, Coding and Freestyle",
        ],
        "use_cases": [
            "Freestyle and Writing",
            "Study and Work",
            "Late Night Drives",
            "Creative Focus",
            "Gaming and Coding",
            "Reading and Relaxing",
            "Beat Sessions",
            "Background Listening",
        ],
        "durations": [
            "12 Hour",
            "Continuous",
            "All Day",
            "Long-Form",
        ],
        "series": [
            "Night Session",
            "Vinyl Beats",
            "Golden Era",
            "Midnight Tape",
            "Street Soul",
            "Late Drive",
            "Dusty Crates",
            "Underground Session",
        ],
        "description_openers": [
            "Welcome to NoLyricsGroove—non-stop instrumental hip hop with no vocals and no interruptions.",
            "Step into a continuous session of dusty drums, deep basslines, vinyl texture, and classic boom bap energy.",
            "NoLyricsGroove delivers old-school-inspired instrumentals for listeners who want beats without vocals.",
            "Press play and settle into raw underground hip hop built around drums, bass, samples, and groove.",
            "This live session blends golden-era influence, jazzy loops, and hard-hitting instrumental rhythm.",
            "A long-form boom bap radio session for beat lovers, writers, creators, and late-night listeners.",
        ],
        "description_middles": [
            "Use the stream for studying, working, writing, freestyle practice, gaming, coding, driving, or creative focus.",
            "Expect dusty drums, warm bass, chopped samples, jazzy details, and an underground East Coast-inspired feel.",
            "The music stays instrumental, making it easy to keep playing in the background without distracting vocals.",
            "Every session draws from an expanding music library, with tracks reordered to keep each broadcast fresh.",
            "This is music for late-night work, freestyle sessions, beat discovery, long drives, and focused creativity.",
            "No talking and no unnecessary interruptions—just a continuous flow of instrumental hip hop.",
        ],
        "description_closers": [
            "Subscribe to NoLyricsGroove for new boom bap sessions, instrumental mixes, and live broadcasts.",
            "New tracks, visuals, sessions, and themed mixes are added regularly.",
            "Stay for the groove, return for the next session, and keep creating.",
            "Turn it up, lock into the rhythm, and enjoy the session.",
        ],
        "hashtags": [
            "#boombap #instrumentalhiphop #90shiphop #hiphopbeats #oldschoolhiphop",
            "#boombapbeats #instrumentalbeats #undergroundhiphop #beats #nolyrics",
            "#goldenera #hiphopinstrumentals #studybeats #freestylebeats #vinylbeats",
            "#oldschool #boom bap #hiphopradio #instrumental #nolyricsgroove",
        ],
    },
}


DEFAULT_TITLES = {
    channel: []
    for channel in CHANNEL_PROFILES
}

DEFAULT_DESCRIPTIONS = {
    channel: []
    for channel in CHANNEL_PROFILES
}


def ensure_metadata_templates(channel_name):
    library = ChannelLibrary(channel_name)
    config = library.get_config()
    changed = False

    if "title_templates" not in config:
        config["title_templates"] = []
        changed = True

    if "description_templates" not in config:
        config["description_templates"] = []
        changed = True

    if "metadata_title_history" not in config:
        config["metadata_title_history"] = []
        changed = True

    if "metadata_description_history" not in config:
        config["metadata_description_history"] = []
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


def clean_items(items):
    return [
        str(item).strip()
        for item in items
        if str(item).strip()
    ]


def trim_history(items):
    return clean_items(items)[-RECENT_HISTORY_LIMIT:]


def pick_without_repeat(items, recent_values):
    values = clean_items(items)
    recent = set(clean_items(recent_values))

    if not values:
        return ""

    candidates = [
        item
        for item in values
        if item not in recent
    ]

    return random.choice(candidates or values)


def render_pattern(pattern, profile):
    values = {}

    key_aliases = {
        "icons": "icon",
        "subjects": "subject",
        "moods": "mood",
        "purposes": "purpose",
        "use_cases": "use_case",
        "durations": "duration",
        "series": "series",
    }

    for key, options in profile.items():
        if key.endswith("_patterns"):
            continue

        if not isinstance(options, list) or not options:
            continue

        output_key = key_aliases.get(key)

        if output_key:
            values[output_key] = random.choice(options)

    return pattern.format(**values).strip()


def generate_title(profile, recent_titles):
    patterns = clean_items(
        profile.get("title_patterns", [])
    )

    recent = set(clean_items(recent_titles))

    for _ in range(GENERATION_ATTEMPTS):
        pattern = random.choice(patterns)
        title = render_pattern(pattern, profile)

        if title not in recent and len(title) <= 100:
            return title

    return render_pattern(
        random.choice(patterns),
        profile,
    )[:100].strip()


def generate_description(profile, recent_descriptions):
    recent = set(clean_items(recent_descriptions))

    for _ in range(GENERATION_ATTEMPTS):
        description = "\n\n".join([
            random.choice(profile["description_openers"]),
            random.choice(profile["description_middles"]),
            random.choice(profile["description_closers"]),
            random.choice(profile["hashtags"]),
        ]).strip()

        if description not in recent:
            return description

    return "\n\n".join([
        random.choice(profile["description_openers"]),
        random.choice(profile["description_middles"]),
        random.choice(profile["description_closers"]),
        random.choice(profile["hashtags"]),
    ]).strip()


def build_generated_metadata(
    channel_name,
    config,
):
    profile = CHANNEL_PROFILES.get(channel_name)

    if not profile:
        return None

    title = generate_title(
        profile,
        config.get("metadata_title_history", []),
    )

    description = generate_description(
        profile,
        config.get("metadata_description_history", []),
    )

    return {
        "title": title,
        "description": description,
    }


def pick_stream_metadata(channel_name):
    library = ChannelLibrary(channel_name)
    config = ensure_metadata_templates(channel_name)

    generated = build_generated_metadata(
        channel_name,
        config,
    )

    if generated:
        title = generated["title"]
        description = generated["description"]
    else:
        title = pick_without_repeat(
            config.get("title_templates", []),
            config.get("metadata_title_history", []),
        )

        description = pick_without_repeat(
            config.get("description_templates", []),
            config.get(
                "metadata_description_history",
                [],
            ),
        )

    if not title:
        title = (
            config.get("title_template")
            or f"{channel_name} Radio LIVE"
        )

    if not description:
        description = (
            config.get("description")
            or f"Welcome to {channel_name}."
        )

    title_history = trim_history(
        config.get("metadata_title_history", [])
        + [title]
    )

    description_history = trim_history(
        config.get(
            "metadata_description_history",
            [],
        )
        + [description]
    )

    config["metadata_title_history"] = title_history
    config["metadata_description_history"] = (
        description_history
    )

    config["last_title_template"] = title
    config["last_description_template"] = description

    # Старые поля сохраняются для интерфейса
    # и обратной совместимости.
    config["title_template"] = title
    config["description"] = description

    library.save_config(config)

    return {
        "title": title,
        "description": description,
    }


def preview_stream_metadata(
    channel_name,
    count=10,
):
    library = ChannelLibrary(channel_name)
    config = deepcopy(
        ensure_metadata_templates(channel_name)
    )

    results = []

    for _ in range(max(1, int(count))):
        generated = build_generated_metadata(
            channel_name,
            config,
        )

        if not generated:
            break

        results.append(generated)

        config["metadata_title_history"] = trim_history(
            config.get(
                "metadata_title_history",
                [],
            )
            + [generated["title"]]
        )

        config["metadata_description_history"] = trim_history(
            config.get(
                "metadata_description_history",
                [],
            )
            + [generated["description"]]
        )

    return results


def templates_to_text(items):
    return "\n---\n".join(clean_items(items))


def text_to_templates(text):
    parts = str(text or "").split("\n---\n")

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]
