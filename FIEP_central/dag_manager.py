# dag_manager.py
# Управление DAG центрального релея FIEP.
# Хранение, обновление, рассылка, сохранение в dag.json.

import json
import os
import threading
import time
from typing import Dict, Any

from centrallogging import CentralLogger

logger = CentralLogger("dag_manager")

DAG_FILE = "dag.json"


class DAGManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.nodes: Dict[str, Dict[str, Any]] = {}

        self._load()

    # ---------------------------------------------------------
    # INTERNAL LOAD/SAVE
    # ---------------------------------------------------------

    def _load(self):
        if not os.path.exists(DAG_FILE):
            logger.info("No dag.json found, starting with empty DAG")
            return

        try:
            with open(DAG_FILE, "r", encoding="utf-8") as f:
                self.nodes = json.load(f)
            logger.info(f"DAG loaded: {len(self.nodes)} nodes")
        except Exception as e:
            logger.error(f"Failed to load dag.json: {e}")

    def _save(self):
        try:
            with open(DAG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.nodes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save dag.json: {e}")

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    def _detect_node_type(self, ip: str) -> str:
        """
        Определяет тип узла:
        - white: белый IP
        - gray: NAT/локальный
        """
        if not ip:
            return "gray"

        # Простейшая проверка на RFC1918
        if ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.16."):
            return "gray"

        return "white"

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def update_node(self, fp: str, data: Dict[str, Any]):
        """
        Обновляет или создаёт запись узла в DAG.
        """
        with self._lock:
            node = self.nodes.get(fp, {})

            # Обновляем поля
            for k, v in data.items():
                if v is not None:
                    node[k] = v

            # last_seen
            node["last_seen"] = int(time.time())

            # node_type
            ip = node.get("address")
            node["node_type"] = self._detect_node_type(ip)

            # relay flag (если порт совпадает с config.PORT)
            if "port" in node and "address" in node:
                node["relay"] = True if node["port"] else False

            self.nodes[fp] = node

            logger.debug(f"DAG updated for {fp}: {node}")

            self._save()

    def merge(self, node_data: Dict[str, Any]):
        """
        Объединяет частичное обновление DAG.
        """
        if not node_data:
            return

        fp = node_data.get("fp")
        if not fp:
            return

        with self._lock:
            node = self.nodes.get(fp, {})
            for k, v in node_data.items():
                if k != "fp" and v is not None:
                    node[k] = v

            node["last_seen"] = int(time.time())
            node["node_type"] = self._detect_node_type(node.get("address"))

            self.nodes[fp] = node

            logger.debug(f"DAG merge for {fp}: {node}")

            self._save()

    def touch(self, fp: str):
        """
        Обновляет last_seen.
        """
        with self._lock:
            if fp in self.nodes:
                self.nodes[fp]["last_seen"] = int(time.time())
                self._save()

    def remove(self, fp: str):
        """
        Удаляет узел из DAG.
        """
        with self._lock:
            if fp in self.nodes:
                del self.nodes[fp]
                logger.info(f"Removed node {fp} from DAG")
                self._save()

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает копию DAG.
        """
        with self._lock:
            return dict(self.nodes)
