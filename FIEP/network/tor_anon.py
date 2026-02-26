import os
import sys
import time
import socket
import subprocess
from pathlib import Path
from typing import Optional

try:
    import socks
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False

from FIEP.network.net_logging import get_network_logger

logger = get_network_logger("FIEP.network.tor")


class TorManager:
    """
    Управляет локальным Tor, создаёт Hidden Service и отдаёт onion‑адрес.
    Работает в трёх режимах:
      1) Использует уже запущенный Tor (SOCKS доступен)
      2) Запускает встроенный tor.exe (Windows)
      3) Запускает системный tor (Linux/macOS)
    """

    def __init__(self, relay_port: int, socks_port: int = 9050, control_port: int = 9051):
        self.relay_port = relay_port
        self.socks_port = socks_port
        self.control_port = control_port

        # каталог tor внутри data_dir FIEP
        self.data_dir = Path(os.path.expanduser("~")) / ".fiep" / "tor"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.hidden_dir = self.data_dir / "hidden_service"
        self.hidden_dir.mkdir(exist_ok=True)

        self.proc: Optional[subprocess.Popen] = None
        self.is_running = False

    @property
    def socks_host(self) -> str:
        return "127.0.0.1"

    # ---------------------------------------------------------
    # Проверка SOCKS
    # ---------------------------------------------------------

    def _check_socks(self) -> bool:
        if not SOCKS_AVAILABLE:
            return False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            s.connect((self.socks_host, self.socks_port))
            s.close()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------
    # Поиск tor.exe или системного tor
    # ---------------------------------------------------------

    def _find_tor(self) -> str:
        """
        Ищет tor.exe рядом с приложением (Windows) или системный tor.
        """
        base = Path(sys.argv[0]).resolve().parent
        candidates = [
            base / "tor" / "tor.exe",
            base / "Tor" / "tor.exe",
            base / "tor" / "bin" / "tor.exe",
        ]

        for c in candidates:
            if c.exists():
                return str(c)

        # Linux/macOS: системный tor
        return "tor"

    # ---------------------------------------------------------
    # Генерация torrc
    # ---------------------------------------------------------

    def _torrc(self) -> Path:
        torrc = self.data_dir / "torrc"

        content = f"""
SocksPort {self.socks_port}
ControlPort {self.control_port}
CookieAuthentication 1

DataDirectory {self.data_dir / 'data'}
CacheDirectory {self.data_dir / 'cache'}

Log notice file {self.data_dir / 'tor.log'}

HiddenServiceDir {self.hidden_dir}
HiddenServicePort {self.relay_port} 127.0.0.1:{self.relay_port}
"""
        torrc.write_text(content, encoding="utf-8")
        return torrc

    # ---------------------------------------------------------
    # Запуск Tor
    # ---------------------------------------------------------

    def start(self) -> bool:
        if not SOCKS_AVAILABLE:
            logger.warning("PySocks not installed, Tor disabled")
            return False

        # если Tor уже работает — используем его
        if self._check_socks():
            logger.info("Using existing Tor SOCKS at %s:%s", self.socks_host, self.socks_port)
            self.is_running = True
            return True

        tor_exe = self._find_tor()
        torrc = self._torrc()

        try:
            startupinfo = None
            creationflags = 0

            # Windows: скрыть окно tor.exe
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            self.proc = subprocess.Popen(
                [tor_exe, "-f", str(torrc)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                cwd=str(self.data_dir),
                startupinfo=startupinfo,
                creationflags=creationflags,
            )

            # ждём запуска SOCKS
            for _ in range(40):
                if self._check_socks():
                    self.is_running = True
                    logger.info("Tor started on %s:%s", self.socks_host, self.socks_port)
                    return True
                time.sleep(1)

            logger.error("Tor did not start within timeout")
            return False

        except Exception as e:
            logger.error("Tor start failed: %s", e)
            return False

    # ---------------------------------------------------------
    # Остановка Tor
    # ---------------------------------------------------------

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                pass
        self.is_running = False

    # ---------------------------------------------------------
    # Onion‑адрес
    # ---------------------------------------------------------

    def get_onion_address(self) -> Optional[str]:
        """
        Возвращает onion‑адрес Hidden Service.
        """
        hostname = self.hidden_dir / "hostname"
        if hostname.exists():
            try:
                return hostname.read_text(encoding="utf-8").strip()
            except Exception:
                return None
        return None

    # ---------------------------------------------------------
    # SOCKS‑сокет
    # ---------------------------------------------------------

    def create_tor_socket(self) -> socket.socket:
        if not SOCKS_AVAILABLE:
            raise RuntimeError("PySocks not installed")
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, self.socks_host, self.socks_port)
        return s
