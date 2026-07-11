import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path("/opt/youtubefactory")


def run_cmd(args, timeout=10):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode,
        }

    except Exception as e:
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(e),
            "code": -1,
        }


def disk_status():
    usage = shutil.disk_usage(PROJECT_ROOT)

    total_gb = round(usage.total / (1024 ** 3), 2)
    free_gb = round(usage.free / (1024 ** 3), 2)
    used_percent = round((usage.used / usage.total) * 100, 1)

    return {
        "ok": free_gb >= 5,
        "total_gb": total_gb,
        "free_gb": free_gb,
        "used_percent": used_percent,
        "message": f"{free_gb} GB свободно из {total_gb} GB",
    }


def memory_status():
    meminfo = {}

    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])
    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
        }

    total_kb = meminfo.get("MemTotal", 0)
    available_kb = meminfo.get("MemAvailable", 0)

    if total_kb <= 0:
        return {
            "ok": False,
            "message": "Не удалось определить RAM",
        }

    used_kb = total_kb - available_kb
    used_percent = round((used_kb / total_kb) * 100, 1)

    return {
        "ok": used_percent < 90,
        "total_gb": round(total_kb / (1024 ** 2), 2),
        "available_gb": round(available_kb / (1024 ** 2), 2),
        "used_percent": used_percent,
        "message": f"RAM занято {used_percent}%",
    }


def cpu_status():
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            load = f.read().strip().split()[0]
    except Exception:
        load = "?"

    return {
        "ok": True,
        "load_1m": load,
        "message": f"Load average 1m: {load}",
    }


def systemd_status():
    result = run_cmd(["systemctl", "--version"])

    return {
        "ok": result["ok"],
        "message": result["stdout"].split("\n")[0] if result["stdout"] else result["stderr"],
    }


def ffmpeg_status():
    result = run_cmd(["ffmpeg", "-version"])

    return {
        "ok": result["ok"],
        "message": result["stdout"].split("\n")[0] if result["stdout"] else result["stderr"],
    }


def python_status():
    return {
        "ok": True,
        "message": sys.version.split()[0],
    }


def project_status():
    required_paths = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "workers",
        PROJECT_ROOT / "library",
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "logs",
    ]

    missing = [
        str(path)
        for path in required_paths
        if not path.exists()
    ]

    return {
        "ok": len(missing) == 0,
        "message": "структура проекта корректна" if not missing else "не найдены: " + ", ".join(missing),
        "missing": missing,
    }


def telegram_status():
    config_path = PROJECT_ROOT / "config" / "telegram.json"

    if not config_path.exists():
        return {
            "ok": False,
            "message": "telegram.json отсутствует",
        }

    try:
        import json

        data = json.loads(config_path.read_text(encoding="utf-8"))
        ok = bool(data.get("enabled")) and bool(data.get("bot_token")) and bool(data.get("chat_id"))

        return {
            "ok": ok,
            "message": "подключен" if ok else "не настроен полностью",
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
        }


def service_status(service_name):
    result = run_cmd(["systemctl", "is-active", service_name])

    return {
        "ok": result["stdout"] == "active",
        "message": result["stdout"] or result["stderr"],
    }


def collect_server_diagnostics():
    checks = [
        {"key": "project", "label": "Project", **project_status()},
        {"key": "python", "label": "Python", **python_status()},
        {"key": "ffmpeg", "label": "FFmpeg", **ffmpeg_status()},
        {"key": "systemd", "label": "Systemd", **systemd_status()},
        {"key": "disk", "label": "Disk", **disk_status()},
        {"key": "ram", "label": "RAM", **memory_status()},
        {"key": "cpu", "label": "CPU", **cpu_status()},
        {"key": "telegram", "label": "Telegram", **telegram_status()},
        {"key": "dashboard_service", "label": "Dashboard service", **service_status("youtubefactory")},
        {"key": "telegram_bot_service", "label": "Telegram bot service", **service_status("youtubefactory-telegram-bot")},
    ]

    failed = [item for item in checks if not item.get("ok")]

    return {
        "ok": len(failed) == 0,
        "checks": checks,
        "failed": failed,
    }


def format_server_diagnostics():
    result = collect_server_diagnostics()

    lines = [
        "🖥 Диагностика сервера",
        "",
    ]

    for item in result["checks"]:
        icon = "✅" if item.get("ok") else "❌"
        lines.append(f"{icon} {item['label']}: {item.get('message', '')}")

    if result["ok"]:
        lines.extend(["", "🟢 Сервер выглядит готовым к работе."])
    else:
        lines.extend(["", "🔴 Найдены проблемы:"])

        for item in result["failed"]:
            lines.append(f"• {item['label']}: {item.get('message', '')}")

    return "\n".join(lines), result
