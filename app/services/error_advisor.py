def analyze_error(error_text):
    text = str(error_text or "")
    lower = text.lower()

    default = {
        "title": "Неизвестная ошибка",
        "what_happened": "Система столкнулась с ошибкой, которую пока нельзя точно классифицировать.",
        "recommended_actions": [
            "Откройте журнал событий и технические детали ошибки.",
            "Проверьте музыку, видео, YouTube-подключение и свободное место на сервере.",
            "После исправления нажмите «Сбросить аварию» и запустите канал снова.",
        ],
        "severity": "critical",
    }

    rules = [
        {
            "keywords": ["no loop videos found", "no loop video"],
            "title": "Нет loop-видео",
            "what_happened": "В папке loop_videos выбранного канала нет ни одного видео для трансляции.",
            "recommended_actions": [
                "Загрузите хотя бы одно loop-видео.",
                "Используйте MP4, MOV, WEBM или MKV.",
                "Нажмите «Сбросить аварию» и запустите канал снова.",
            ],
        },
        {
            "keywords": ["no music found", "no audio found"],
            "title": "Нет музыки",
            "what_happened": "В музыкальной папке канала нет треков для эфира.",
            "recommended_actions": [
                "Загрузите музыку.",
                "Используйте MP3, WAV, M4A, AAC или FLAC.",
                "Нажмите «Сбросить аварию» и запустите канал снова.",
            ],
        },
        {
            "keywords": [
                "media larger than",
                "mediauploadsizeerror",
                "thumbnail larger than",
                "larger than: 2097152",
            ],
            "title": "Превью слишком большое",
            "what_happened": "YouTube не принял превью из-за превышения допустимого размера.",
            "recommended_actions": [
                "Сожмите превью до размера меньше 2 МБ.",
                "Используйте JPG 1280×720, 16:9.",
                "Загрузите новое превью и снова запустите канал.",
            ],
        },
        {
            "keywords": [
                "userrequestsexceedratelimit",
                "user requests exceed the rate limit",
                "rate limit",
            ],
            "title": "Превышен лимит YouTube API",
            "what_happened": "YouTube временно ограничил запросы из-за слишком частых запусков или изменений.",
            "recommended_actions": [
                "Не запускайте канал много раз подряд.",
                "Подождите 15–60 минут.",
                "Проверьте зависшие трансляции на YouTube.",
                "После паузы сбросьте аварию и запустите канал снова.",
            ],
        },
        {
            "keywords": [
                "unauthorized",
                "invalid_grant",
                "credentials",
                "refresh token",
                "oauth",
                "401",
                "token has been expired or revoked",
            ],
            "title": "Проблема авторизации YouTube",
            "what_happened": "YouTube OAuth-токен не работает или доступ был отозван.",
            "recommended_actions": [
                "Откройте настройки YouTube.",
                "Переподключите YouTube.",
                "Пройдите авторизацию Google заново.",
                "После подключения запустите канал снова.",
            ],
        },
        {
            "keywords": [
                "no space left",
                "disk full",
                "enospc",
                "диск: свободно",
            ],
            "title": "Закончилось место на диске",
            "what_happened": "На сервере недостаточно свободного места для работы проекта.",
            "recommended_actions": [
                "Удалите ненужные архивы, временные файлы и старые логи.",
                "Проверьте место командой: df -h /",
                "После освобождения места сбросьте аварию и запустите канал снова.",
            ],
        },
        {
            "keywords": [
                "broken pipe",
                "rtmp-соединение",
                "rtmp_broken_pipe",
                "error writing trailer: broken pipe",
            ],
            "title": "RTMP-соединение с YouTube разорвано",
            "what_happened": "YouTube или сеть закрыли RTMP-соединение. Система должна попытаться восстановить эфир автоматически.",
            "recommended_actions": [
                "Подождите, пока система создаст новый эфир автоматически.",
                "Если пришло сообщение об успешном восстановлении — ничего делать не нужно.",
                "Ваше участие требуется только если система сообщит, что автоматические попытки исчерпаны.",
            ],
            "severity": "warning",
        },
        {
            "keywords": [
                "connection reset",
                "connection refused",
                "timed out",
                "timeout",
                "network is unreachable",
                "temporary failure in name resolution",
            ],
            "title": "Проблема сети",
            "what_happened": "Сервер временно потерял соединение. Система сначала попытается восстановиться автоматически.",
            "recommended_actions": [
                "Подождите автоматического восстановления.",
                "Если восстановление успешно — ничего делать не нужно.",
                "Если попытки исчерпаны, проверьте интернет и firewall сервера.",
            ],
            "severity": "warning",
        },
        {
            "keywords": [
                "exiting normally, received signal 15",
                "manual_stop",
                "штатная остановка ffmpeg",
            ],
            "title": "Штатная остановка",
            "what_happened": "FFmpeg был остановлен вручную или через systemctl stop. Это не авария.",
            "recommended_actions": [
                "Ничего исправлять не нужно.",
                "Для продолжения эфира запустите канал снова.",
            ],
            "severity": "info",
        },
        {
            "keywords": [
                "access_not_configured",
                "youtube data api has not been used",
                "api has not been used",
            ],
            "title": "YouTube API не настроен",
            "what_happened": "Google или YouTube API не разрешает запросы для этого проекта.",
            "recommended_actions": [
                "Проверьте, что YouTube Data API v3 включён.",
                "Проверьте OAuth consent screen.",
                "Переподключите YouTube и запустите канал снова.",
            ],
        },
        {
            "keywords": [
                "ffmpeg",
                "conversion failed",
                "invalid data found",
                "error while decoding",
                "corrupt input packet",
            ],
            "title": "Ошибка FFmpeg или повреждённый медиафайл",
            "what_happened": "FFmpeg не смог корректно обработать один из аудио- или видеофайлов.",
            "recommended_actions": [
                "Проверьте последние загруженные треки и видео.",
                "Удалите подозрительный файл и загрузите его заново.",
                "Для видео используйте MP4 H.264, 30 FPS, 16:9.",
                "После исправления сбросьте аварию и запустите канал снова.",
            ],
        },
    ]

    for rule in rules:
        if any(keyword in lower for keyword in rule["keywords"]):
            return {
                "title": rule["title"],
                "what_happened": rule["what_happened"],
                "recommended_actions": rule["recommended_actions"],
                "severity": rule.get("severity", "critical"),
            }

    return default


def format_advice(error_text):
    advice = analyze_error(error_text)
    actions = "\n".join(
        f"{idx}. {item}"
        for idx, item in enumerate(advice["recommended_actions"], start=1)
    )
    return (
        f"Причина: {advice['title']}\n\n"
        f"Что произошло:\n{advice['what_happened']}\n\n"
        f"Что сделать:\n{actions}"
    )
