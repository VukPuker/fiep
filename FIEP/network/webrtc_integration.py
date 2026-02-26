# webrtc_integration.py
# Интеграция WebRTC с транспортным уровнем FIEP.

import json
import base64
import time
from typing import Callable, Dict, Any, Optional, Set

from FIEP.network.net_logging import get_network_logger
from FIEP.network.webrtc import WebRTCManager

logger = get_network_logger("FIEP.network.webrtc_integration")


class WebRTCIntegration:
    """
    Инкапсулирует WebRTC-логику:
      - отправка сигналинга через relay
      - приём сигналинга
      - авто-коннекты по DAG
      - приём сообщений WebRTC DataChannel
    """

    def __init__(
        self,
        fingerprint: str,
        signaling_send: Callable[[Dict[str, Any]], None],
        on_message: Callable[[str, bytes], None],
        dag_lookup_all: Callable[[], Dict[str, Any]],
    ):
        self.fingerprint = fingerprint
        self.signaling_send = signaling_send
        self.on_message = on_message
        self.dag_lookup_all = dag_lookup_all

        self.webrtc = WebRTCManager(
            local_fp=fingerprint,
            signaling_send=self._send_signal,
            on_message=self._on_webrtc_message,
            ice_servers=[{"urls": "stun:stun.l.google.com:19302"}],
        )

        # чтобы не спамить connect_to() на один и тот же fp
        self._attempted: Set[str] = set()

    # ---------------------------------------------------------
    # SIGNALING
    # ---------------------------------------------------------

    def _send_signal(self, remote_fp: str, signal: Dict[str, Any]):
        """
        Отправка WebRTC-сигналинга через relay.
        """
        try:
            payload = base64.b64encode(
                json.dumps(signal).encode("utf-8")
            ).decode("ascii")

            env = {
                "type": "message",
                "from": self.fingerprint,
                "to": remote_fp,
                "payload": payload,
                "timestamp": int(time.time()),
                "offline": True,
                "webrtc": True,
            }

            self.signaling_send(env)
            logger.debug("WebRTCIntegration: sent signaling → %s", remote_fp[:8])

        except Exception as e:
            logger.error("WebRTCIntegration: signaling send error: %s", e)

    # ---------------------------------------------------------
    # MESSAGE FROM WEBRTC
    # ---------------------------------------------------------

    def _on_webrtc_message(self, sender_fp: str, data: bytes):
        """
        Сообщение пришло по WebRTC DataChannel → отдаём в приложение.
        """
        try:
            self.on_message(sender_fp, data)
        except Exception as e:
            logger.error("WebRTCIntegration: message handler error: %s", e)

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def handle_signal(self, sender_fp: str, signal: Dict[str, Any]):
        """
        Приём сигналинга, пришедшего через relay.
        """
        try:
            if not isinstance(signal, dict):
                logger.error("WebRTCIntegration: invalid signaling format from %s", sender_fp)
                return

            self.webrtc.handle_signal(sender_fp, signal)

        except Exception as e:
            logger.error("WebRTCIntegration: signaling parse error: %s", e)

    def connect(self, fp: str):
        """
        Ручное подключение к узлу.
        """
        if fp == self.fingerprint:
            return

        try:
            self.webrtc.connect_to(fp)
            logger.info("WebRTCIntegration: manual connect → %s", fp[:8])
        except Exception as e:
            logger.error("WebRTCIntegration: connect error: %s", e)

    # ---------------------------------------------------------
    # AUTO-CONNECT
    # ---------------------------------------------------------

    def auto_connect(self):
        """
        Автоматически инициирует WebRTC-каналы с узлами из DAG.
        """
        dag_nodes = self.dag_lookup_all()
        if not dag_nodes:
            return

        for fp, node in dag_nodes.items():
            if fp == self.fingerprint:
                continue

            # уже пытались
            if fp in self._attempted:
                continue

            # узел должен иметь TCP-адрес (иначе WebRTC бессмысленен)
            if not getattr(node, "address", None) or not getattr(node, "port", None):
                continue

            # узел должен поддерживать WebRTC
            if hasattr(node, "supports_webrtc") and not getattr(node, "supports_webrtc", True):
                continue

            try:
                self.webrtc.connect_to(fp)
                self._attempted.add(fp)
                logger.info("WebRTCIntegration: auto-connect → %s", fp[:8])
            except Exception as e:
                logger.error("WebRTCIntegration: auto-connect error for %s: %s", fp[:8], e)

    # ---------------------------------------------------------
    # SHUTDOWN
    # ---------------------------------------------------------

    def shutdown(self):
        try:
            self.webrtc.shutdown()
        except Exception as e:
            logger.error("WebRTCIntegration: shutdown error: %s", e)

        self._attempted.clear()
