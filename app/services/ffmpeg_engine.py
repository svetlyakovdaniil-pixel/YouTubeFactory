import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.services.ffmpeg_analyzer import analyze_ffmpeg_output, write_ffmpeg_log


@dataclass
class FFmpegResult:
    ok: bool
    returncode: Optional[int]
    output: str
    log_paths: dict
    analysis: dict
    started_at: str
    finished_at: str
    duration_seconds: float


@dataclass
class FFmpegProcess:
    process: subprocess.Popen
    output_chunks: List[str] = field(default_factory=list)
    reader_thread: Optional[threading.Thread] = None
    started_at: float = field(default_factory=time.time)

    def is_running(self):
        return self.process.poll() is None

    def returncode(self):
        return self.process.poll()


class FFmpegEngine:

    def __init__(self, channel_name):
        self.channel_name = channel_name

    def _reader(self, process, output_chunks, max_chars=250000):
        if not process.stdout:
            return

        fd = process.stdout.fileno()
        total = sum(len(item) for item in output_chunks)

        while True:
            try:
                chunk = os.read(fd, 4096)
            except Exception:
                break

            if not chunk:
                break

            text = chunk.decode("utf-8", errors="replace")
            output_chunks.append(text)
            total += len(text)

            while total > max_chars and output_chunks:
                removed = output_chunks.pop(0)
                total -= len(removed)

    def _output_text(self, ffmpeg_process):
        return "".join(ffmpeg_process.output_chunks)

    def start(self, command, context=None):
        context = context or {}

        header_lines = [
            "COMMAND:",
            " ".join(command[:-1] + ["<RTMP_URL_HIDDEN>"]) if command else "",
            "",
        ]

        for key, value in context.items():
            header_lines.append(f"{key}: {value}")

        header_lines.append("")
        header = "\n".join(header_lines)

        write_ffmpeg_log(self.channel_name, header, archive=False)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )

        ffmpeg_process = FFmpegProcess(
            process=process,
            started_at=time.time(),
        )

        ffmpeg_process.output_chunks.append(header + "\n")

        thread = threading.Thread(
            target=self._reader,
            args=(process, ffmpeg_process.output_chunks),
            daemon=True,
        )
        thread.start()
        ffmpeg_process.reader_thread = thread

        return ffmpeg_process

    def snapshot_log(self, ffmpeg_process):
        output = self._output_text(ffmpeg_process)
        return write_ffmpeg_log(self.channel_name, output, archive=False)

    def stop(self, ffmpeg_process, timeout=15):
        if not ffmpeg_process.is_running():
            return ffmpeg_process.returncode()

        ffmpeg_process.process.terminate()

        try:
            ffmpeg_process.process.wait(timeout=timeout)
        except Exception:
            ffmpeg_process.process.kill()
            ffmpeg_process.process.wait()

        if ffmpeg_process.reader_thread:
            ffmpeg_process.reader_thread.join(timeout=3)

        self.snapshot_log(ffmpeg_process)
        return ffmpeg_process.returncode()

    def wait_until_finished_or_flag_removed(self, ffmpeg_process, flag_path, tick_seconds=1):
        started = ffmpeg_process.started_at
        started_iso = datetime.fromtimestamp(started, tz=timezone.utc).isoformat()

        while Path(flag_path).exists():
            code = ffmpeg_process.returncode()

            self.snapshot_log(ffmpeg_process)

            if code is not None:
                break

            time.sleep(tick_seconds)

        if not Path(flag_path).exists() and ffmpeg_process.is_running():
            self.stop(ffmpeg_process)

        if ffmpeg_process.reader_thread:
            ffmpeg_process.reader_thread.join(timeout=3)

        output = self._output_text(ffmpeg_process)
        log_paths = write_ffmpeg_log(self.channel_name, output, archive=True)

        code = ffmpeg_process.returncode()
        finished = time.time()
        finished_iso = datetime.fromtimestamp(finished, tz=timezone.utc).isoformat()

        analysis = analyze_ffmpeg_output(code, output)
        ok = code == 0 or analysis.get("type") == "manual_stop"

        return FFmpegResult(
            ok=ok,
            returncode=code,
            output=output,
            log_paths=log_paths,
            analysis=analysis,
            started_at=started_iso,
            finished_at=finished_iso,
            duration_seconds=round(finished - started, 2),
        )
