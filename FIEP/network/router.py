# router.py
# Маршрутизация сообщений FIEP:
# WebRTC → UDP → локальный relay → TCP → Tor → fallback

import json
import socket
import base64
import time
from typing import Optional, Dict, Any, Callable, Tuple

from FIEP.network.net_logging import get_network_logger


logger = get_network_logger("FIEP.network.router")


class Router:
    """
    Отвечает за выбор маршрута доставки:
      1) WebRTC (если есть прямой канал)
      2) UDP P2P (hole-punching)
      3) Локальный relay (DynamicRelayNode)
      4) Прямой TCP по DAG
      5) Tor (если включён)
    """

    def __init__(
        self,
        fingerprint: str,
        webrtc_send: Callable[[str, bytes], bool],
        udp_send: Callable[[str, bytes], bool],
        udp_available: Callable[[str], bool],
        relay_send: Callable[[Dict[str, Any]], bool],
        dag_lookup: Callable[[str], Optional[Any]],
        tor_socket_factory: Optional[Callable[[], socket.socket]] = None,
        mode: str = "relay",
    ):
        self.fingerprint = fingerprint
        self.webrtc_send = webrtc_send
        self.udp_send = udp_send
        self.udp_available = udp_available
        self.relay_send = relay_send
        self.dag_lookup = dag_lookup
        self.tor_socket_factory = tor_socket_factory
        self.mode = mode  # normal / tor / p2p / relay

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def send(self, recipient_fp: str, ciphertext: bytes) -> bool:
        """
        Высокоуровневый метод:
        выбирает маршрут и отправляет сообщение.
        """

        # 1) WebRTC
        if self._try_webrtc(recipient_fp, ciphertext):
            return True

        # 2) UDP P2P
        if self._try_udp_p2p(recipient_fp, ciphertext):
            return True

        # 3) Локальный relay
        if self._try_local_relay(recipient_fp, ciphertext):
            return True

        # 4) Прямой TCP по DAG
        if self._try_direct_tcp(recipient_fp, ciphertext):
            return True

        # 5) Tor (если включён)
        if self._try_tor(recipient_fp, ciphertext):
            return True

        logger.warning("Router: no route for %s", recipient_fp[:8])
        return False

    # ---------------------------------------------------------
    # ROUTE ATTEMPTS
    # ---------------------------------------------------------

    def _try_webrtc(self, fp: str, ciphertext: bytes) -> bool:
        try:
            if self.webrtc_send(fp, ciphertext):
                logger.info("Router: sent via WebRTC → %s", fp[:8])
                return True
        except Exception as e:
            logger.error("Router: WebRTC error: %s", e)
        return False

    def _try_udp_p2p(self, fp: str, ciphertext: bytes) -> bool:
        if not self.udp_available(fp):
            return False
        try:
            if self.udp_send(fp, ciphertext):
                logger.info("Router: sent via UDP P2P → %s", fp[:8])
                return True
        except Exception as e:
            logger.error("Router: UDP P2P error: %s", e)
        return False

    def _try_local_relay(self, fp: str, ciphertext: bytes) -> bool:
        env = self._make_env(fp, ciphertext)
        try:
            if self.relay_send(env):
                logger.info("Router: sent via local relay → %s", fp[:8])
                return True
        except Exception as e:
            logger.error("Router: local relay error: %s", e)
        return False

    def _try_direct_tcp(self, fp: str, ciphertext: bytes) -> bool:
        node = self.dag_lookup(fp)
        if not node:
            return False

        if not getattr(node, "address", None) or not getattr(node, "port", None):
            return False

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((node.address, node.port))
            s.sendall(json.dumps(self._make_env(fp, ciphertext)).encode("utf-8"))
            s.close()
            logger.info("Router: sent via direct TCP → %s", fp[:8])
            return True
        except Exception as e:
            logger.error("Router: direct TCP error: %s", e)
            return False

    def _try_tor(self, fp: str, ciphertext: bytes) -> bool:
        if self.mode != "tor":
            return False
        if not self.tor_socket_factory:
            return False

        node = self.dag_lookup(fp)
        if not node:
            return False

        if getattr(node, "address_type", "ip") != "onion":
            return False

        try:
            s = self.tor_socket_factory()
            s.settimeout(10)
            s.connect((node.address, node.port))
            s.sendall(json.dumps(self._make_env(fp, ciphertext)).encode("utf-8"))
            s.close()
            logger.info("Router: sent via Tor → %s", fp[:8])
            return True
        except Exception as e:
            logger.error("Router: Tor send error: %s", e)
            return False

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    def _make_env(self, fp: str, ciphertext: bytes) -> Dict[str, Any]:
        return {
            "type": "message",
            "from": self.fingerprint,
            "to": fp,
            "payload": base64.b64encode(ciphertext).decode("ascii"),
            "timestamp": int(time.time()),
            "offline": True,
        }
