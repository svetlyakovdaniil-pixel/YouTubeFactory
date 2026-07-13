import random
import socket
import time
from http.client import RemoteDisconnected

from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError


TRANSIENT_HTTP_STATUSES = {
    408,
    429,
    500,
    502,
    503,
    504,
}

TRANSIENT_TEXT_MARKERS = (
    "remote end closed connection",
    "connection reset",
    "connection aborted",
    "connection refused",
    "network is unreachable",
    "temporary failure in name resolution",
    "name or service not known",
    "timed out",
    "timeout",
    "server disconnected",
    "broken pipe",
    "sslerror",
    "eof occurred",
    "backend error",
    "internal error",
    "rate limit",
)


class TemporaryYouTubeApiError(RuntimeError):
    """Временная ошибка сети или сервера YouTube API."""


def iter_exception_chain(exc):
    visited = set()
    current = exc

    while current is not None:
        identity = id(current)

        if identity in visited:
            break

        visited.add(identity)
        yield current

        current = (
            current.__cause__
            or current.__context__
        )


def is_transient_youtube_error(exc):
    for current in iter_exception_chain(exc):
        if isinstance(
            current,
            (
                TransportError,
                RemoteDisconnected,
                TimeoutError,
                ConnectionError,
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
                socket.timeout,
            ),
        ):
            return True

        if isinstance(current, HttpError):
            status = getattr(
                current.resp,
                "status",
                None,
            )

            if status in TRANSIENT_HTTP_STATUSES:
                return True

        text = (
            f"{type(current).__name__}: {current}"
        ).lower()

        if any(
            marker in text
            for marker in TRANSIENT_TEXT_MARKERS
        ):
            return True

    return False


def safe_execute(
    request,
    *,
    operation_name="YouTube API request",
    max_attempts=8,
    initial_delay=5,
    max_delay=120,
):
    """
    Выполняет Google API request.execute() с повторными
    попытками только при временных сетевых ошибках.

    Ошибки авторизации вроде invalid_grant не маскируются
    и сразу передаются вызывающему коду.
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return request.execute(
                num_retries=3,
            )

        except Exception as exc:
            if not is_transient_youtube_error(exc):
                raise

            last_error = exc

            if attempt >= max_attempts:
                break

            base_delay = min(
                initial_delay * (2 ** (attempt - 1)),
                max_delay,
            )

            jitter = random.uniform(
                0,
                min(3, base_delay * 0.2),
            )

            time.sleep(base_delay + jitter)

    raise TemporaryYouTubeApiError(
        f"{operation_name} временно недоступен после "
        f"{max_attempts} попыток: {last_error}"
    ) from last_error
