# udp_punch.py
# UDP hole-punching для FIEP.
# Пробивает NAT и устанавливает прямой UDP-канал между двумя узлами.

import socket
import threading
import time
from typing import Callable, Optional, Tuple

from FIEP.network.net_logging import get_network_logger

logger = get_network_logger("FIEP.network.udp_punch")


STUN_SERVER = ("stun.l.google.com", 19302)


class UDPPuncher:
    """
    Реализует UDP hole-punching:
      - определяет внешний UDP-порт через STUN
      - слушает локальный UDP-порт
      - пробивает NAT, отправляя пустые пакеты
      - принимает входящие UDP-сообщения
    """

    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.local_port: Optional[int] = None
        self.external_ip: Optional[str] = None
        self.external_port: Optional[int] = None

        self.running = False
        self.thread: Optional[threading.Thread] = None

        self.on_message: Optional[Callable[[bytes, Tuple[str, int]], None]] = None

    # ---------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------

    def start(self, on_message: Callable[[bytes, Tuple[str, int]], None]):
        """
        Запускает UDP listener и определяет внешний порт.
        """
        if self.running:
            return

        self.on_message = on_message

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.local_port = self.sock.getsockname()[1]

        self.running = True

        # Определяем внешний порт через STUN
        self._detect_external_port()

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

        logger.info(
            "UDPPuncher started: local_port=%s external=%s:%s",
            self.local_port,
            self.external_ip,
            self.external_port,
        )

    def stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    # ---------------------------------------------------------
    # STUN
    # ---------------------------------------------------------

    def _detect_external_port(self):
        """
        Простейший STUN-запрос (RFC 5389).
        Возвращает внешний IP и порт.
        """
        try:
            stun_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            stun_sock.settimeout(3)

            # STUN Binding Request
            req = b"\x00\x01" + b"\x00\x00" + b"\x21\x12\xa4\x42" + b"\x00" * 12
            stun_sock.sendto(req, STUN_SERVER)

            data, addr = stun_sock.recvfrom(2048)

            # Ответ STUN содержит XOR-MAPPED-ADDRESS (упрощённый парсинг)
            if data[0:2] == b"\x01\x01" and len(data) >= 28:
                port = (data[-4] << 8) + data[-3]
                ip = f"{data[-8]}.{data[-7]}.{data[-6]}.{data[-5]}"

                self.external_ip = ip
                self.external_port = port

            stun_sock.close()

        except Exception as e:
            logger.error("STUN error: %s", e)
            self.external_ip = None
            self.external_port = None

    # ---------------------------------------------------------
    # LISTENER
    # ---------------------------------------------------------

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65536)
            except Exception:
                continue

            if self.on_message:
                try:
                    self.on_message(data, addr)
                except Exception as e:
                    logger.error("UDP message handler error: %s", e)

    # ---------------------------------------------------------
    # HOLE PUNCH
    # ---------------------------------------------------------

    def punch(self, remote_ip: str, remote_port: int):
        """
        Пробивает NAT, отправляя пустые UDP-пакеты на удалённый адрес.
        """
        if not self.sock:
            return

        logger.info("UDP punch → %s:%s", remote_ip, remote_port)

        for _ in range(5):
            try:
                self.sock.sendto(b"", (remote_ip, remote_port))
            except Exception:
                pass
            time.sleep(0.2)

    # ---------------------------------------------------------
    # SEND
    # ---------------------------------------------------------

    def send(self, data: bytes, remote_ip: str, remote_port: int) -> bool:
        """
        Отправка данных по UDP.
        """
        if not self.sock:
            return False

        try:
            self.sock.sendto(data, (remote_ip, remote_port))
            return True
        except Exception as e:
            logger.error("UDP send error: %s", e)
            return False
