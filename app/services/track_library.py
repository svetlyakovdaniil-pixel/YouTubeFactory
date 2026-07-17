import hashlib
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from app.services.channel_library import ChannelLibrary


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}

DEFAULT_TAXONOMIES = {
    "NoLyricsGroove": {
        "genres": {
            "Hip-Hop": [
                "Boom Bap",
                "Lo-Fi Hip-Hop",
                "Dark Hip-Hop",
                "West Coast Hip-Hop",
                "G-Funk",
                "East Coast Hip-Hop",
                "Underground Hip-Hop",
                "Jazz Rap",
                "Chill Hip-Hop",
                "Soulful Hip-Hop",
                "Cinematic Hip-Hop",
                "Trap Instrumental",
                "Memphis Hip-Hop",
                "Phonk",
                "Cloud Rap",
                "Experimental Hip-Hop",
                "Old School Hip-Hop",
                "Modern Boom Bap",
            ]
        },
        "moods": [
            "Aggressive",
            "Dark",
            "Chill",
            "Energetic",
            "Mysterious",
            "Relaxing",
            "Uplifting",
            "Warm",
        ],
    },
    "Cosmic Slumber": {
        "genres": {
            "Ambient": [
                "Space Ambient",
                "Sleep Ambient",
                "Dark Ambient",
                "Meditation Ambient",
                "Drone Ambient",
                "Cinematic Ambient",
            ]
        },
        "moods": [
            "Calm",
            "Dreamy",
            "Mysterious",
            "Relaxing",
            "Warm",
        ],
    },
}

FALLBACK_TAXONOMY = {
    "genres": {
        "Other": [
            "Other",
        ]
    },
    "moods": [
        "Calm",
        "Dark",
        "Energetic",
        "Relaxing",
    ],
}


class TrackLibrary:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.library = ChannelLibrary(channel_name)
        self.taxonomy_path = (
            self.library.metadata_dir
            / "music_taxonomy.json"
        )
        self.ensure_taxonomy()

    def _normalise_name(self, value):
        return " ".join(str(value or "").strip().split())

    def _default_taxonomy(self):
        source = DEFAULT_TAXONOMIES.get(
            self.channel_name,
            FALLBACK_TAXONOMY,
        )

        return {
            "genres": {
                genre: list(subgenres)
                for genre, subgenres
                in source["genres"].items()
            },
            "moods": list(source["moods"]),
        }

    def ensure_taxonomy(self):
        if self.taxonomy_path.exists():
            taxonomy = self.get_taxonomy()
            self.save_taxonomy(taxonomy)
            return

        self.save_taxonomy(self._default_taxonomy())

    def get_taxonomy(self):
        taxonomy = self.library.read_json(
            self.taxonomy_path,
            self._default_taxonomy(),
        )

        genres = taxonomy.get("genres", {})
        moods = taxonomy.get("moods", [])

        cleaned_genres = {}

        for genre, subgenres in genres.items():
            clean_genre = self._normalise_name(genre)

            if not clean_genre:
                continue

            clean_subgenres = []

            for subgenre in subgenres or []:
                clean_subgenre = self._normalise_name(
                    subgenre
                )

                if (
                    clean_subgenre
                    and clean_subgenre not in clean_subgenres
                ):
                    clean_subgenres.append(
                        clean_subgenre
                    )

            if not clean_subgenres:
                clean_subgenres = ["Other"]

            cleaned_genres[clean_genre] = clean_subgenres

        if not cleaned_genres:
            cleaned_genres = {
                "Other": ["Other"]
            }

        cleaned_moods = []

        for mood in moods:
            clean_mood = self._normalise_name(mood)

            if clean_mood and clean_mood not in cleaned_moods:
                cleaned_moods.append(clean_mood)

        if not cleaned_moods:
            cleaned_moods = ["Other"]

        return {
            "genres": cleaned_genres,
            "moods": cleaned_moods,
        }

    def save_taxonomy(self, taxonomy):
        self.library.write_json(
            self.taxonomy_path,
            taxonomy,
        )

    def add_genre(self, genre):
        genre = self._normalise_name(genre)

        if not genre:
            raise ValueError(
                "Название жанра не может быть пустым."
            )

        taxonomy = self.get_taxonomy()
        taxonomy["genres"].setdefault(
            genre,
            ["Other"],
        )
        self.save_taxonomy(taxonomy)

    def delete_genre(self, genre):
        taxonomy = self.get_taxonomy()

        if genre not in taxonomy["genres"]:
            return

        if len(taxonomy["genres"]) <= 1:
            raise ValueError(
                "Нельзя удалить последний жанр."
            )

        del taxonomy["genres"][genre]
        self.save_taxonomy(taxonomy)

    def add_subgenre(self, genre, subgenre):
        subgenre = self._normalise_name(subgenre)

        if not subgenre:
            raise ValueError(
                "Название поджанра не может быть пустым."
            )

        taxonomy = self.get_taxonomy()

        if genre not in taxonomy["genres"]:
            raise ValueError("Жанр не найден.")

        if subgenre not in taxonomy["genres"][genre]:
            taxonomy["genres"][genre].append(
                subgenre
            )

        self.save_taxonomy(taxonomy)

    def delete_subgenre(self, genre, subgenre):
        taxonomy = self.get_taxonomy()
        subgenres = taxonomy["genres"].get(
            genre,
            [],
        )

        if subgenre not in subgenres:
            return

        if len(subgenres) <= 1:
            raise ValueError(
                "Нельзя удалить последний поджанр жанра."
            )

        taxonomy["genres"][genre] = [
            item
            for item in subgenres
            if item != subgenre
        ]
        self.save_taxonomy(taxonomy)

    def add_mood(self, mood):
        mood = self._normalise_name(mood)

        if not mood:
            raise ValueError(
                "Название настроения не может быть пустым."
            )

        taxonomy = self.get_taxonomy()

        if mood not in taxonomy["moods"]:
            taxonomy["moods"].append(mood)

        self.save_taxonomy(taxonomy)

    def delete_mood(self, mood):
        taxonomy = self.get_taxonomy()

        if mood not in taxonomy["moods"]:
            return

        if len(taxonomy["moods"]) <= 1:
            raise ValueError(
                "Нельзя удалить последнее настроение."
            )

        taxonomy["moods"] = [
            item
            for item in taxonomy["moods"]
            if item != mood
        ]
        self.save_taxonomy(taxonomy)

    def _safe_filename(self, filename):
        name = Path(filename).name
        stem = Path(name).stem
        suffix = Path(name).suffix.lower()

        if suffix not in AUDIO_EXTENSIONS:
            raise ValueError(
                f"Неподдерживаемый аудиоформат: "
                f"{suffix or 'без расширения'}"
            )

        stem = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            stem,
        )
        stem = re.sub(
            r"\s+",
            " ",
            stem,
        ).strip(" ._")

        if not stem:
            stem = "track"

        return f"{stem}{suffix}"

    def _unique_destination(self, filename):
        destination = (
            self.library.music_dir
            / filename
        )

        if not destination.exists():
            return destination

        stem = destination.stem
        suffix = destination.suffix

        for index in range(2, 10000):
            candidate = destination.with_name(
                f"{stem}_{index}{suffix}"
            )

            if not candidate.exists():
                return candidate

        raise RuntimeError(
            f"Не удалось создать уникальное имя "
            f"для {filename}"
        )

    def _sha256_bytes(self, payload):
        return hashlib.sha256(
            payload
        ).hexdigest()

    def _metadata_path(self, audio_path):
        return self.library.music_metadata_path(
            audio_path
        )

    def _default_metadata(self, audio_path):
        return {
            "channel": self.channel_name,
            "filename": audio_path.name,
            "path": str(audio_path),
            "title": audio_path.stem,
            "genre": "",
            "subgenre": "",
            "mood": "",
            "bpm": None,
            "sha256": "",
            "uploaded_at": "",
            "updated_at": "",
            "live_enabled": True,
            "vod_enabled": True,
            "live_uses": 0,
            "vod_uses": 0,
            "last_live_at": "",
            "last_vod_at": "",
        }

    def load_metadata(self, audio_path):
        audio_path = Path(audio_path)
        path = self._metadata_path(audio_path)

        metadata = self.library.read_json(
            path,
            self._default_metadata(audio_path),
        )
        defaults = self._default_metadata(
            audio_path
        )

        for key, value in defaults.items():
            metadata.setdefault(key, value)

        metadata["filename"] = audio_path.name
        metadata["path"] = str(audio_path)
        metadata.pop("artist", None)

        return metadata

    def save_metadata(self, audio_path, metadata):
        audio_path = Path(audio_path)
        current = self.load_metadata(audio_path)
        current.update(metadata)
        current.pop("artist", None)
        current["filename"] = audio_path.name
        current["path"] = str(audio_path)
        current["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        self.library.write_json(
            self._metadata_path(audio_path),
            current,
        )

        return current

    def find_duplicate(self, sha256):
        for audio_path in self.library.list_music():
            metadata = self.load_metadata(
                audio_path
            )

            if metadata.get("sha256") == sha256:
                return audio_path

        return None

    def upload_tracks(
        self,
        uploaded_files,
        genre,
        subgenre,
        mood,
        bpm=None,
    ):
        taxonomy = self.get_taxonomy()

        if genre not in taxonomy["genres"]:
            raise ValueError(
                "Выбранный жанр отсутствует "
                "в настройках канала."
            )

        if subgenre not in taxonomy["genres"][genre]:
            raise ValueError(
                "Выбранный поджанр отсутствует "
                "в настройках канала."
            )

        if mood not in taxonomy["moods"]:
            raise ValueError(
                "Выбранное настроение отсутствует "
                "в настройках канала."
            )

        results = []

        for uploaded_file in uploaded_files:
            try:
                payload = uploaded_file.getvalue()

                if not payload:
                    raise ValueError("Файл пустой.")

                sha256 = self._sha256_bytes(
                    payload
                )
                duplicate = self.find_duplicate(
                    sha256
                )

                if duplicate:
                    results.append(
                        {
                            "ok": True,
                            "duplicate": True,
                            "filename": uploaded_file.name,
                            "path": str(duplicate),
                        }
                    )
                    continue

                filename = self._safe_filename(
                    uploaded_file.name
                )
                destination = (
                    self._unique_destination(
                        filename
                    )
                )
                destination.write_bytes(payload)

                now = datetime.now(
                    timezone.utc
                ).isoformat()

                metadata = self._default_metadata(
                    destination
                )
                metadata.update(
                    {
                        "title": destination.stem,
                        "genre": genre,
                        "subgenre": subgenre,
                        "mood": mood,
                        "bpm": (
                            int(bpm)
                            if bpm
                            else None
                        ),
                        "sha256": sha256,
                        "uploaded_at": now,
                        "updated_at": now,
                    }
                )

                self.library.write_json(
                    self._metadata_path(
                        destination
                    ),
                    metadata,
                )

                results.append(
                    {
                        "ok": True,
                        "duplicate": False,
                        "filename": destination.name,
                        "path": str(destination),
                    }
                )

            except Exception as error:
                results.append(
                    {
                        "ok": False,
                        "duplicate": False,
                        "filename": uploaded_file.name,
                        "error": str(error),
                    }
                )

        return results

    def list_tracks(self):
        tracks = []

        for audio_path in self.library.list_music():
            metadata = self.load_metadata(
                audio_path
            )
            tracks.append(
                {
                    "audio_path": audio_path,
                    "metadata": metadata,
                }
            )

        return sorted(
            tracks,
            key=lambda item: (
                item["audio_path"].name.lower()
            ),
        )

    def select_vod_candidates(
        self,
        genre,
        subgenre,
        mood=None,
    ):
        candidates = []

        for item in self.list_tracks():
            metadata = item["metadata"]

            if not metadata.get(
                "vod_enabled",
                True,
            ):
                continue

            if metadata.get("genre") != genre:
                continue

            if metadata.get("subgenre") != subgenre:
                continue

            if (
                mood
                and metadata.get("mood") != mood
            ):
                continue

            candidates.append(item)

        random.shuffle(candidates)

        candidates.sort(
            key=lambda item: int(
                item["metadata"].get(
                    "vod_uses",
                    0,
                )
                or 0
            )
        )

        return candidates

    def mark_vod_used(
        self,
        audio_paths,
        publication_id="",
    ):
        now = datetime.now(
            timezone.utc
        ).isoformat()
        updated = []

        for audio_path in audio_paths:
            audio_path = Path(audio_path)

            if not audio_path.exists():
                continue

            metadata = self.load_metadata(
                audio_path
            )
            metadata["vod_uses"] = int(
                metadata.get(
                    "vod_uses",
                    0,
                )
                or 0
            ) + 1
            metadata["last_vod_at"] = now

            if publication_id:
                history = metadata.setdefault(
                    "vod_publication_ids",
                    [],
                )

                if publication_id not in history:
                    history.append(
                        publication_id
                    )

            updated.append(
                self.save_metadata(
                    audio_path,
                    metadata,
                )
            )

        return updated

    def delete_track(self, audio_path):
        audio_path = Path(audio_path)
        metadata_path = self._metadata_path(
            audio_path
        )

        if audio_path.exists():
            audio_path.unlink()

        if metadata_path.exists():
            metadata_path.unlink()
