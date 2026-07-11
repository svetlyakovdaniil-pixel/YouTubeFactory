import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.channel_library import ChannelLibrary
from app.services.radio_service import RadioService
from app.services.telegram_notifier import notify_info, notify_warning, notify_error
from app.services.event_log import add_event
from app.services.error_advisor import analyze_error, format_advice
from app.services.preflight_manager import assert_preflight_ok
from app.services.metadata_manager import pick_stream_metadata
from app.services.ffmpeg_analyzer import format_ffmpeg_analysis
from app.youtube.publish import Publisher


LOG_FILE = Path("/opt/youtubefactory/logs/live_worker.log")
MAX_AUTO_RECOVERY_ATTEMPTS = 3
AUTO_RECOVERY_DELAY_SECONDS = 15
STABLE_STREAM_SECONDS = 300


def log(message):
    print(message, flush=True)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def event(channel, level, message, data=None):
    add_event(
        channel=channel,
        level=level,
        message=message,
        data=data or {},
    )


def set_state(channel, **kwargs):
    library = ChannelLibrary(channel)
    state = library.get_state()
    state.update(kwargs)
    library.save_state(state)


def reset_state(channel):
    set_state(
        channel,
        running=False,
        watch_url="",
        started_at="",
        current_track="",
        track_index=0,
    )


def pause_channel(channel, error):
    runtime = Path("/opt/youtubefactory/runtime")
    flag = runtime / f"{channel}.running"

    if flag.exists():
        flag.unlink()

    set_state(
        channel,
        running=False,
        paused=True,
        watch_url="",
        started_at="",
        current_track="",
        track_index=0,
        last_error=error[-2000:],
    )

    advice_text = format_advice(error)

    notify_error(
        channel,
        "Канал остановлен и ожидает вашего вмешательства.\n\n"
        f"{advice_text}\n\n"
        f"Технические детали:\n{error[-1200:]}",
    )


def clear_pause(channel):
    set_state(
        channel,
        paused=False,
        last_error="",
    )


def run(channel):
    runtime = Path("/opt/youtubefactory/runtime")
    runtime.mkdir(parents=True, exist_ok=True)

    flag = runtime / f"{channel}.running"

    log(f"===== Radio Worker started: {channel} =====")
    event(channel, "info", "Воркер запущен")

    clear_pause(channel)

    library = ChannelLibrary(channel)
    radio = RadioService(channel)
    publisher = Publisher()

    auto_recovery_attempt = 0
    recovering = False

    while flag.exists():
        try:
            config = library.get_config()

            duration_hours = int(
                config.get(
                    "stream_duration_hours",
                    12,
                )
            )

            set_state(
                channel,
                running=True,
                stream_duration_hours=duration_hours,
                last_error="",
            )

            event(channel, "info", "Preflight Check перед запуском")
            assert_preflight_ok(channel)
            event(channel, "success", "Preflight Check пройден")

            event(channel, "info", "Сборка плейлиста")
            playlist = radio.build_playlist()

            event(
                channel,
                "info",
                "Плейлист готов",
                {
                    "tracks": len(playlist.get("tracks", [])),
                    "total_seconds": playlist.get("total_seconds", 0),
                },
            )

            metadata = pick_stream_metadata(channel)
            title = metadata["title"]
            description = metadata["description"]

            event(
                channel,
                "info",
                "Выбраны название и описание эфира",
                {
                    "title": title,
                    "description": description,
                },
            )

            event(
                channel,
                "info",
                "Создание YouTube Live после автовосстановления" if recovering else "Создание YouTube Live",
                {"recovery_attempt": auto_recovery_attempt if recovering else 0},
            )

            result = publisher.publish_radio(
                channel_name=channel,
                playlist=playlist,
                title=title,
                description=description,
            )

            set_state(
                channel,
                running=True,
                paused=False,
                watch_url=result["watch_url"],
                started_at=now_iso(),
                current_track=playlist["tracks"][0]["title"],
                track_index=1,
                last_error="",
            )

            event(
                channel,
                "success",
                "Эфир автоматически восстановлен" if recovering else "Эфир успешно запущен",
                {
                    "watch_url": result["watch_url"],
                    "current_track": playlist["tracks"][0]["title"],
                    "thumbnail_path": result.get("thumbnail_path", ""),
                    "recovery_attempt": auto_recovery_attempt if recovering else 0,
                },
            )

            if recovering:
                notify_info(
                    channel,
                    "✅ Трансляция автоматически восстановлена.\n\n"
                    "Ваше участие не потребовалось.\n\n"
                    f"{result['watch_url']}",
                )
                recovering = False
            else:
                notify_info(
                    channel,
                    "✅ Эфир успешно запущен.\n\n"
                    f"{result['watch_url']}",
                )

            engine = result["ffmpeg_engine"]
            ffmpeg_process = result["ffmpeg_process"]

            ffmpeg_result = engine.wait_until_finished_or_flag_removed(
                ffmpeg_process,
                flag,
                tick_seconds=1,
            )

            event(
                channel,
                "info" if ffmpeg_result.ok else "warning",
                "FFmpeg завершил работу",
                {
                    "ok": ffmpeg_result.ok,
                    "returncode": ffmpeg_result.returncode,
                    "duration_seconds": ffmpeg_result.duration_seconds,
                    "analysis": ffmpeg_result.analysis,
                    "ffmpeg_log": ffmpeg_result.log_paths,
                },
            )

            if not flag.exists():
                reset_state(channel)
                event(channel, "info", "Эфир остановлен пользователем")
                break

            analysis = ffmpeg_result.analysis or {}
            action = analysis.get("action", "need_user")

            if ffmpeg_result.duration_seconds >= STABLE_STREAM_SECONDS:
                auto_recovery_attempt = 0

            if ffmpeg_result.ok:
                reset_state(channel)
                event(channel, "info", "Эфир завершён. Создаётся следующий эфир")
                recovering = True
                time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                continue

            if action == "stop":
                reset_state(channel)
                event(channel, "info", "FFmpeg остановлен штатно")
                break

            if action == "restart_broadcast":
                auto_recovery_attempt += 1

                if auto_recovery_attempt > MAX_AUTO_RECOVERY_ATTEMPTS:
                    raise RuntimeError(
                        "Автоматическое восстановление не удалось после "
                        f"{MAX_AUTO_RECOVERY_ATTEMPTS} попыток.\n\n"
                        + format_ffmpeg_analysis(analysis)
                        + "\n\n"
                        + f"FFmpeg log: {ffmpeg_result.log_paths.get('latest')}"
                    )

                reset_state(channel)
                set_state(channel, paused=False, last_error="")

                event(
                    channel,
                    "warning",
                    "Запущено автоматическое восстановление эфира",
                    {
                        "attempt": auto_recovery_attempt,
                        "max_attempts": MAX_AUTO_RECOVERY_ATTEMPTS,
                        "analysis": analysis,
                        "ffmpeg_log": ffmpeg_result.log_paths,
                    },
                )

                notify_warning(
                    channel,
                    f"{analysis.get('title', 'Соединение с YouTube прервано')}.\n\n"
                    f"{analysis.get('what_happened', '')}\n\n"
                    "Система уже создаёт новый эфир автоматически.\n"
                    f"Попытка {auto_recovery_attempt} из {MAX_AUTO_RECOVERY_ATTEMPTS}.\n\n"
                    "Ничего делать не нужно.",
                )

                recovering = True
                time.sleep(AUTO_RECOVERY_DELAY_SECONDS)
                continue

            raise RuntimeError(
                "FFmpeg failed\n\n"
                + format_ffmpeg_analysis(analysis)
                + "\n\n"
                + f"FFmpeg log: {ffmpeg_result.log_paths.get('latest')}"
            )

        except Exception:
            error = traceback.format_exc()
            log(error)

            advice = analyze_error(error)

            event(
                channel,
                "error",
                "Критическая ошибка. Канал переведён в режим ожидания",
                {
                    "error_title": advice["title"],
                    "what_happened": advice["what_happened"],
                    "recommended_actions": advice["recommended_actions"],
                    "error": error[-2000:],
                },
            )

            pause_channel(channel, error)
            log(f"[{channel}] Critical error. Channel paused. Waiting for manual restart.")
            break

    reset_state(channel)
    event(channel, "info", "Воркер остановлен")
    log(f"===== Radio Worker stopped: {channel} =====")


if __name__ == "__main__":
    run(sys.argv[1])
