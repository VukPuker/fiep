# stun_detect.py
# Определение WAN IP через api.ipify.org, проверка порта, DDNS-обновление.

import socket
import time
import threading
from typing import Optional

from centrallogging import CentralLogger
from config import PORT, DDNS_ENABLED, STUN_SERVERS
from ddns_update import update_ddns, get_public_ip

logger = CentralLogger("stun_detect")


class StunDetector:
    """
    Определяет WAN IP через ipify (надёжно при заблокированном UDP),
    проверяет порт через STUN (если UDP доступен),
    вызывает DDNS при изменении IP.
    """

    def __init__(self):
        self.current_ip: Optional[str] = None

    # ---------------------------------------------------------
    # OPTIONAL: STUN PORT CHECK (если UDP доступен)
    # ---------------------------------------------------------

    def _stun_port_check(self) -> bool:
        """
        Пробует отправить STUN-запросы, чтобы проверить доступность UDP.
        Не используется для определения IP — только для проверки порта.
        """
        for stun in STUN_SERVERS:
            try:
                host, port = stun.split(":")
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(2)

                req = b"\x00\x01" + b"\x00\x00" + b"\x21\x12\xa4\x42" + b"\x00" * 12
                sock.sendto(req, (host, int(port)))

                sock.recvfrom(2048)
                sock.close()
                return True  # UDP работает
            except Exception:
                continue

        return False  # UDP заблокирован

    # ---------------------------------------------------------
    # PORT CHECK (TCP)
    # ---------------------------------------------------------

    def check_port(self, wan_ip: str, port: int) -> bool:
        """
        Проверяет, открыт ли порт релея снаружи.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((wan_ip, port))
            s.close()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------
    # MAIN CHECK
    # ---------------------------------------------------------

    def check(self):
        """
        Выполняет один цикл проверки:
        - определяет WAN IP через ipify
        - проверяет порт
        - вызывает DDNS при изменении
        """
        wan_ip = get_public_ip()

        if not wan_ip:
            logger.warning("Cannot detect WAN IP via ipify")
            return

        if wan_ip != self.current_ip:
            logger.info(f"WAN IP changed: {self.current_ip} → {wan_ip}")
            self.current_ip = wan_ip

            if DDNS_ENABLED:
                update_ddns()

        # Проверка TCP-порта
        if self.check_port(wan_ip, PORT):
            logger.info(f"Port {PORT} is reachable from WAN ({wan_ip})")
        else:
            logger.warning(f"Port {PORT} is NOT reachable from WAN ({wan_ip})")

        # Проверка UDP (опционально)
        if self._stun_port_check():
            logger.info("UDP connectivity: OK")
        else:
            logger.warning("UDP connectivity: BLOCKED")

    # ---------------------------------------------------------
    # BACKGROUND THREAD
    # ---------------------------------------------------------

    def start_background(self, interval: int = 60):
        """
        Запускает периодическую проверку в отдельном потоке.
        """
        def loop():
            while True:
                try:
                    self.check()
                except Exception as e:
                    logger.error(f"STUN/IP check error: {e}")
                time.sleep(interval)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        logger.info("WAN-IP detector started in background")
