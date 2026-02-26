# webrtc_signaling.py
# Пересылка WebRTC SDP/ICE сигналов между узлами через центральный relay.

import json
from typing import Dict, Any

from centrallogging import CentralLogger

logger = CentralLogger("webrtc_signaling")


class WebRTCSignaling:
    """
    Обрабатывает WebRTC signaling envelopes:
      {
        "type": "webrtc",
        "from": "fp1",
        "to": "fp2",
        "payload": "<base64>"
      }
    """

    def __init__(self, dag_manager):
        self.dag = dag_manager

    async def forward(self, env: Dict[str, Any], clients: Dict[str, Any]):
        """
        Пересылает WebRTC сигнал нужному клиенту.
        Обновляет DAG: webrtc=true для обоих узлов.
        """
        sender = env.get("from")
        target = env.get("to")

        if not sender or not target:
            logger.warning(f"Invalid WebRTC envelope: {env}")
            return

        # Обновляем DAG: WebRTC канал активен
        self.dag.update_node(sender, {"webrtc": True})
        self.dag.update_node(target, {"webrtc": True})

        # Пересылка
        if target not in clients:
            logger.warning(f"WebRTC target {target} not connected")
            return

        try:
            writer = clients[target]
            writer.write((json.dumps(env) + "\n").encode())
            await writer.drain()

            logger.info(f"WebRTC signal forwarded {sender} → {target}")

        except Exception as e:
            logger.error(f"Failed to forward WebRTC signal to {target}: {e}")
