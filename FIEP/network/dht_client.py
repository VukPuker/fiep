# dht_client.py
# Минимальный DHT-клиент для FIEP.
# Отвечает за:
#   - bootstrap к DHT-нодам
#   - публикацию собственного адреса
#   - поиск адресов других узлов
#   - простые K/V операции
#
# НЕ занимается:
#   - NAT
#   - WebRTC
#   - UDP hole-punching
#   - relay
#   - маршрутизацией
#   - DAG
#
# Это чистый DHT-клиент, который можно заменить на Kademlia/Chord в будущем.

import json
import socket
import time
from typing import Optional, Dict, Any, List, Tuple

from FIEP.network.net_logging import get_network_logger

logger = get_network_logger("FIEP.network.dht_client")


class DHTClient:
    """
    Минимальный DHT-клиент:
      - bootstrap к DHT-нодам
      - публикация собственного адреса
      - поиск адресов других узлов
      - простые K/V операции
    """

    def __init__(
        self,
        fingerprint: str,
        bootstrap_nodes: List[Tuple[str, int]],
        timeout: float = 5.0,
    ):
        self.fingerprint = fingerprint
        self.bootstrap_nodes = bootstrap_nodes
        self.timeout = timeout

        # Кэш найденных узлов
        self.cache: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------
    # LOW-LEVEL TCP
    # ---------------------------------------------------------

    def _send_request(self, host: str, port: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Отправляет JSON-запрос на DHT-нод и получает JSON-ответ.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((host, port))

            s.sendall(json.dumps(payload).encode("utf-8"))

            raw = s.recv(65536)
            s.close()

            if not raw:
                return None

            return json.loads(raw.decode("utf-8"))

        except Exception as e:
            logger.error("DHTClient: request error to %s:%s: %s", host, port, e)
            return None

    # ---------------------------------------------------------
    # BOOTSTRAP
    # ---------------------------------------------------------

    def bootstrap(self) -> bool:
        """
        Проверяет доступность хотя бы одного bootstrap-узла.
        """
        for host, port in self.bootstrap_nodes:
            resp = self._send_request(host, port, {"type": "ping"})
            if resp and resp.get("type") == "pong":
                logger.info("DHTClient: bootstrap OK via %s:%s", host, port)
                return True

        logger.warning("DHTClient: bootstrap failed")
        return False

    # ---------------------------------------------------------
    # PUBLISH SELF
    # ---------------------------------------------------------

    def publish_self(self, address: str, port: int, udp_port: Optional[int] = None):
        """
        Публикует собственный адрес в DHT.
        """
        payload = {
            "type": "store",
            "key": self.fingerprint,
            "value": {
                "address": address,
                "port": port,
                "udp_port": udp_port,
                "timestamp": int(time.time()),
            },
        }

        for host, port_ in self.bootstrap_nodes:
            self._send_request(host, port_, payload)

        logger.info("DHTClient: published self → %s:%s", address, port)

    # ---------------------------------------------------------
    # LOOKUP
    # ---------------------------------------------------------

    def lookup(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """
        Ищет адрес узла по fingerprint.
        """
        # 1) Кэш
        if fingerprint in self.cache:
            return self.cache[fingerprint]

        # 2) DHT-запрос
        payload = {"type": "lookup", "key": fingerprint}

        for host, port in self.bootstrap_nodes:
            resp = self._send_request(host, port, payload)
            if resp and resp.get("type") == "result":
                value = resp.get("value")
                if value:
                    self.cache[fingerprint] = value
                    return value

        return None

    # ---------------------------------------------------------
    # GENERIC K/V
    # ---------------------------------------------------------

    def store(self, key: str, value: Any):
        """
        Сохраняет произвольное значение в DHT.
        """
        payload = {"type": "store", "key": key, "value": value}

        for host, port in self.bootstrap_nodes:
            self._send_request(host, port, payload)

    def get(self, key: str) -> Optional[Any]:
        """
        Получает произвольное значение из DHT.
        """
        payload = {"type": "lookup", "key": key}

        for host, port in self.bootstrap_nodes:
            resp = self._send_request(host, port, payload)
            if resp and resp.get("type") == "result":
                return resp.get("value")

        return None
