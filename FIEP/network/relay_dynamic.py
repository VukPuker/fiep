# relay_dynamic.py
# Локальный динамический relay-узел FIEP.
# Принимает входящие TCP-соединения, передаёт envelopes в TransportLayer,
# обновляет DAG, пересылает сообщения напрямую или через центральный relay.

import json
import socket
import threading
import time
from typing import Callable, Dict, Any, Optional, List

from FIEP.network.net_logging import get_network_logger
from FIEP.network.dag import DAG

logger = get_network_logger("FIEP.network.relay_dynamic")


class DynamicRelayNode:
    """
    Локальный relay-узел FIEP.
    Он:
      - принимает входящие TCP-соединения
      - передаёт envelopes в TransportLayer
      - обновляет DAG
      - пересылает сообщения напрямую или через центральный relay
      - НЕ интерпретирует WebRTC-сигналинг
    """

    def __init__(self, fingerprint: str, peer_id: str, dht, central_host: str, central_port: int):
        self.fingerprint = fingerprint
        self.peer_id = peer_id
        self.dht = dht  # не используется, но оставлено для совместимости API

        self.central_host = central_host
        self.central_port = central_port

        self.local_ip: Optional[str] = None
        self.public_ip: Optional[str] = None

        self.port: Optional[int] = None
        self.server_socket: Optional[socket.socket] = None

        self.handlers: List[Callable[[Dict[str, Any]], None]] = []

        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Новый DAG
        self.dag = DAG()

    # ---------------------------------------------------------
    # PUBLIC IP UPDATE
    # ---------------------------------------------------------

    def update_public_ip(self, ip: str):
        self.public_ip = ip
        logger.info("DynamicRelayNode: public IP updated → %s", ip)

    # ---------------------------------------------------------
    # HANDLERS
    # ---------------------------------------------------------

    def add_handler(self, handler: Callable[[Dict[str, Any]], None]):
        self.handlers.append(handler)

    def _dispatch(self, env: Dict[str, Any]):
        for h in self.handlers:
            try:
                h(env)
            except Exception as e:
                logger.error("DynamicRelayNode: handler error: %s", e)

    # ---------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------

    def start(self):
        if self.running:
            return

        self.running = True

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("0.0.0.0", 0))
        self.server_socket.listen(50)
        self.port = self.server_socket.getsockname()[1]

        logger.info("DynamicRelayNode started on port %s", self.port)

        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass

    # ---------------------------------------------------------
    # ACCEPT LOOP
    # ---------------------------------------------------------

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server_socket.accept()
            except Exception:
                continue

            threading.Thread(
                target=self._client_thread,
                args=(client,),
                daemon=True
            ).start()

    # ---------------------------------------------------------
    # CLIENT HANDLER
    # ---------------------------------------------------------

    def _client_thread(self, sock: socket.socket):
        try:
            raw = sock.recv(65536)
        except Exception:
            sock.close()
            return

        sock.close()

        try:
            env = json.loads(raw.decode("utf-8"))
        except Exception:
            return

        etype = env.get("type")

        # -----------------------------------------------------
        # MESSAGE (включая WebRTC-сигналинг)
        # -----------------------------------------------------
        if etype == "message":
            self._dispatch(env)
            return

        # -----------------------------------------------------
        # DAG UPDATE
        # -----------------------------------------------------
        if etype == "dag":
            try:
                remote_dag = env.get("dag", {})
                if isinstance(remote_dag, dict):
                    self.dag.merge(remote_dag)
                    logger.info("DynamicRelayNode: DAG merged (%d nodes)", len(remote_dag))
            except Exception as e:
                logger.error("DynamicRelayNode: DAG update error: %s", e)
            return

        # -----------------------------------------------------
        # UDP-INFO / OTHER
        # -----------------------------------------------------
        self._dispatch(env)

    # ---------------------------------------------------------
    # SEND
    # ---------------------------------------------------------

    def send_envelope(self, env: Dict[str, Any]):
        """
        Отправка envelope:
          - если адресат в DAG → TCP напрямую
          - иначе → через центральный relay
        """

        target_fp = env.get("to")
        if not target_fp:
            return False

        node = self.dag.nodes.get(target_fp)

        # direct TCP
        if node and getattr(node, "address", None) and getattr(node, "port", None):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((node.address, node.port))
                s.sendall(json.dumps(env).encode("utf-8"))
                s.close()
                return True
            except Exception:
                pass

        # fallback → central relay
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self.central_host, self.central_port))
            s.sendall(json.dumps(env).encode("utf-8"))
            s.close()
            return True
        except Exception as e:
            logger.error("DynamicRelayNode: central relay send error: %s", e)
            return False

    # ---------------------------------------------------------
    # DAG HANDLER (from central relay)
    # ---------------------------------------------------------

    def _handle_dag(self, env: Dict[str, Any]):
        try:
            remote_dag = env.get("dag", {})
            if isinstance(remote_dag, dict):
                self.dag.merge(remote_dag)
                logger.info("DynamicRelayNode: DAG merged (%d nodes)", len(remote_dag))
        except Exception as e:
            logger.error("DynamicRelayNode: DAG update error: %s", e)
