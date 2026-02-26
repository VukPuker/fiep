# centrallogging.py
# Централизованное логирование для central_relay.
# Пишет в консоль и в logs/logs.txt, потокобезопасно.

import os
import threading
import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "logs.txt")


class CentralLogger:
    _lock = threading.Lock()

    def __init__(self, name: str, level: str = "INFO"):
        self.name = name
        self.level = level.upper()

        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)

    # -------------------------
    # INTERNAL
    # -------------------------

    def _should_log(self, level: str) -> bool:
        order = ["DEBUG", "INFO", "WARNING", "ERROR"]
        return order.index(level) >= order.index(self.level)

    def _write(self, level: str, msg: str):
        if not self._should_log(level):
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] [{self.name}] {msg}"

        with CentralLogger._lock:
            # Консоль
            print(line)

            # Файл
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    # -------------------------
    # PUBLIC API
    # -------------------------

    def debug(self, msg: str):
        self._write("DEBUG", msg)

    def info(self, msg: str):
        self._write("INFO", msg)

    def warning(self, msg: str):
        self._write("WARNING", msg)

    def error(self, msg: str):
        self._write("ERROR", msg)
