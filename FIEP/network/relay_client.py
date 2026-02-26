# relay_client.py
# Клиент для подключения к центральному / bootstrap / fallback relay.
# Работает в отдельном потоке, принимает DAG и любые envelopes, вызывает callback’и.

import json
import socket
import threading
import time
from typing import Callable, Dict, Any, Optional, List, Tuple

from FIEP.network.net_logging import get_network_logger


logger = get_network_logger("FIEP.network.relay_client")


class RelayClient:
    """
    Клиент релея:
      - подключается к центральному relay
      - fallback → bootstrap relay
      - fallback → relay из DAG
      - регистрируется
      - шлёт ping
      - принимает MESSAGE, DAG, UDP-INFO и др.
      - вызывает callback’и в TransportLayer
    """

    def __init__(
        self,
        fingerprint: str,
        local_ip: str,
        external_ip: Optional[str],
        relay_port: int,
        get_bootstrap_nodes: Callable[[], List[Tuple[str, int]]],
        get_fallback_relays: Callable[[], List[Tuple[str, int]]],
        on_message: Callable[[Dict[str, Any]], None],
        on_dag: Callable[[Dict[str, Any]], None],
        central_host: Optional[str],
        central_port: Optional[int],
    ):
        self.fingerprint = fingerprint
        self.local_ip = local_ip
        self.external_ip = external_ip
        self.relay_port = relay_port

        self.get_bootstrap_nodes = get_bootstrap_nodes
        self.get_fallback_relays = get_fallback_relays

        self.on_message = on_message
        self.on_dag = on_dag

        self.central_host = central_host
        self.central_port = central_port

        self.running = False
        self.thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------

    def start(self):
        if self.running:
            return
        self.running = True

        self.thread = threading.Thread(target=self._manager_loop, daemon=True)
        self.thread.start()

        logger.info("RelayClient started")

    def stop(self):
        self.running = False
        logger.info("RelayClient stopped")

    # ---------------------------------------------------------
    # MAIN MANAGER LOOP
    # ---------------------------------------------------------

    def _manager_loop(self):
        """
        Алгоритм:
        1) пробуем центральный relay
        2) пробуем bootstrap relay
        3) пробуем fallback relay из DAG
        4) повторяем
        """
        while self.running:
            # 1) Центральный relay
            if self.central_host and self.central_port:
                if self._relay_loop(self.central_host, self.central_port):
                    time.sleep(5)
                    continue

            # 2) Bootstrap relay
            for host, port in self.get_bootstrap_nodes():
                if not self.running:
                    break
                if self._relay_loop(host, port):
                    time.sleep(5)
                    break

            # 3) Fallback relay из DAG
            for host, port in self.get_fallback_relays():
                if not self.running:
                    break
                if self._relay_loop(host, port):
                    time.sleep(5)
                    break

            time.sleep(5)

    # ---------------------------------------------------------
    # RELAY LOOP
    # ---------------------------------------------------------

    def _relay_loop(self, host: str, port: int) -> bool:
        """
        Подключение к relay:
          - регистрация
          - ping
          - приём MESSAGE, DAG и других envelopes
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((host, port))

            register_env = {
                "type": "register",
                "fingerprint": self.fingerprint,
                "port": self.relay_port,
                "public_ip": self.external_ip,
                "local_ip": self.local_ip,
                "supports_webrtc": True,
            }

            s.sendall(json.dumps(register_env).encode("utf-8"))

            last_ping = time.time()

            while self.running:
                s.settimeout(5)
                try:
                    raw = s.recv(65536)
                except socket.timeout:
                    raw = b""
                except Exception:
                    break

                now = time.time()
                if now - last_ping > 30:
                    try:
                        s.sendall(json.dumps({"type": "ping"}).encode("utf-8"))
                    except Exception:
                        break
                    last_ping = now

                if not raw:
                    continue

                try:
                    env = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue

                etype = env.get("type")

                if etype == "dag":
                    self.on_dag(env)
                    continue

                # Всё остальное (message, udp-info, служебные) отдаём в on_message
                self.on_message(env)

            try:
                s.close()
            except Exception:
                pass

            return True

        except Exception as e:
            logger.error("RelayClient: connection error (%s:%s): %s", host, port, e)
            return False
