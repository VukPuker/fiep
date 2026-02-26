# udp_registry.py
# Хранение UDP-координат узлов и обновление DAG.

import time
from typing import Dict, Any

from centrallogging import CentralLogger

logger = CentralLogger("udp_registry")


class UDPRegistry:
    """
    Хранит UDP-координаты узлов:
      - внешний IP
      - внешний порт
      - timestamp
    Обновляет DAG через dag_manager.
    """

    def __init__(self, dag_manager):
        self.dag = dag_manager
        self.udp_nodes: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def update(self, fp: str, env: Dict[str, Any]):
        """
        Обрабатывает envelope вида:
        {
            "type": "udp-info",
            "from": "fp",
            "external_ip": "...",
            "external_port": 58395,
            "timestamp": 1730000000
        }
        """

        ip = env.get("external_ip")
        port = env.get("external_port")

        if not ip or not port:
            logger.warning(f"Invalid UDP info from {fp}: {env}")
            return

        now = int(time.time())

        self.udp_nodes[fp] = {
            "ip": ip,
            "port": int(port),
            "timestamp": now
        }

        logger.info(f"UDP updated for {fp}: {ip}:{port}")

        # Обновляем DAG
        self.dag.update_node(fp, {
            "udp_ip": ip,
            "udp_port": int(port),
            "last_seen": now
        })

    def get(self, fp: str):
        """
        Возвращает UDP-координаты узла.
        """
        return self.udp_nodes.get(fp)

    def cleanup(self, max_age: int = 120):
        """
        Удаляет устаревшие UDP-координаты.
        max_age — время в секундах.
        """
        now = int(time.time())
        to_delete = []

        for fp, info in self.udp_nodes.items():
            if now - info["timestamp"] > max_age:
                to_delete.append(fp)

        for fp in to_delete:
            logger.info(f"UDP expired for {fp}")
            del self.udp_nodes[fp]

            # Удаляем UDP из DAG
            self.dag.update_node(fp, {
                "udp_ip": None,
                "udp_port": None
            })
