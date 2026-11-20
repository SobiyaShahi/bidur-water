"""Shared log helper: every module logs through here so all lines look alike."""
import threading
import time

_lock = threading.Lock()
_file = None


def setup_file_log(path):
    """Also write every log line to `path`."""
    global _file
    _file = open(path, "a", encoding="utf-8", buffering=1)


def _stamp():
    """Return current UTC time as ISO-8601 with milliseconds and a Z."""
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int((now % 1) * 1000):03d}Z"


def log(node, tag, msg):
    """Print one structured, thread-safe log line and return it."""
    line = f"{_stamp()} [{node}] [{tag:<7}] {msg}"
    with _lock:
        print(line, flush=True)
        if _file:
            _file.write(line + "\n")
    return line