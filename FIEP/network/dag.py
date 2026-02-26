# dag.py
# Локальный Directed Acyclic Graph (DAG) узлов FIEP.
# Хранит информацию о всех известных узлах:
#   - fingerprint
#   - адреса (TCP, UDP, onion)
#   - WebRTC-способности
#   - публичный IP
#   - порт relay
#   - timestamp последнего обновления
#
# НЕ занимается:
#   - маршрутизацией
#   - NAT
#   - WebRTC
#   - UDP
#   - relay
#   - DHT
#
# Это чистая структура данных.

import time
from typing import Dict, Any, Optional

from FIEP.network.net_logging import get_network_logger

logger = get_network_logger("FIEP.network.dag")


class DAGNode:
    """
    Узел DAG — информация об одном участнике сети.
    """

    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint

        # TCP
        self.address: Optional[str] = None
        self.port: Optional[int] = None

        # UDP
        self.udp_ip: Optional[str] = None
        self.udp_port: Optional[int] = None

        # WebRTC
        self.supports_webrtc: bool = False

        # Tor
        self.address_type: str = "ip"  # ip / onion

        # Relay
        self.relay_ip: Optional[str] = None
        self.relay_port: Optional[int] = None

        # Metadata
        self.timestamp: int = int(time.time())

    def update(self, data: Dict[str, Any]):
        """
        Обновляет поля узла.
        """
        changed = False

        for key, value in data.items():
            if hasattr(self, key) and value is not None:
                if getattr(self, key) != value:
                    setattr(self, key, value)
                    changed = True

        if changed:
            self.timestamp = int(time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "address": self.address,
            "port": self.port,
            "udp_ip": self.udp_ip,
            "udp_port": self.udp_port,
            "supports_webrtc": self.supports_webrtc,
            "address_type": self.address_type,
            "relay_ip": self.relay_ip,
            "relay_port": self.relay_port,
            "timestamp": self.timestamp,
        }


class DAG:
    """
    Локальный DAG всех известных узлов.
    """

    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}

    # ---------------------------------------------------------
    # NODE MANAGEMENT
    # ---------------------------------------------------------

    def get_or_create(self, fingerprint: str) -> DAGNode:
        if fingerprint not in self.nodes:
            self.nodes[fingerprint] = DAGNode(fingerprint)
        return self.nodes[fingerprint]

    def update_node(self, fingerprint: str, data: Dict[str, Any]):
        node = self.get_or_create(fingerprint)
        node.update(data)

    def remove_node(self, fingerprint: str):
        if fingerprint in self.nodes:
            del self.nodes[fingerprint]

    # ---------------------------------------------------------
    # MERGE DAG
    # ---------------------------------------------------------

    def merge(self, remote_dag: Dict[str, Any]):
        """
        Объединяет локальный DAG с DAG, полученным от другого узла.
        """
        for fp, node_data in remote_dag.items():
            self.update_node(fp, node_data)

    # ---------------------------------------------------------
    # EXPORT
    # ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {fp: node.to_dict() for fp, node in self.nodes.items()}

    # ---------------------------------------------------------
    # LOOKUP HELPERS
    # ---------------------------------------------------------

    def get_tcp_address(self, fingerprint: str) -> Optional[tuple]:
        node = self.nodes.get(fingerprint)
        if node and node.address and node.port:
            return node.address, node.port
        return None

    def get_udp_address(self, fingerprint: str) -> Optional[tuple]:
        node = self.nodes.get(fingerprint)
        if node and node.udp_ip and node.udp_port:
            return node.udp_ip, node.udp_port
        return None

    def get_relay_address(self, fingerprint: str) -> Optional[tuple]:
        node = self.nodes.get(fingerprint)
        if node and node.relay_ip and node.relay_port:
            return node.relay_ip, node.relay_port
        return None

    def supports_webrtc(self, fingerprint: str) -> bool:
        node = self.nodes.get(fingerprint)
        return bool(node and node.supports_webrtc)
