# transport.py
# Тонкий фасад транспортного уровня FIEP.
# Оркеструет NAT, локальный relay, relay-клиент, WebRTC, UDP hole-punching, DHT и маршрутизацию.

import base64
import json
import time
from typing import Callable, Optional, Dict, Any, Tuple

from FIEP.network.net_logging import get_network_logger
from FIEP.network.nat import NatManager
from FIEP.network.relay_dynamic import DynamicRelayNode
from FIEP.network.relay_client import RelayClient
from FIEP.network.router import Router
from FIEP.network.webrtc_integration import WebRTCIntegration
from FIEP.network.tor_anon import TorManager
from FIEP.network.udp_punch import UDPPuncher
from FIEP.network.dht_client import DHTClient
from FIEP.core.config import config

logger = get_network_logger("FIEP.network.transport")


class NetworkMode:
    NORMAL = "normal"
    TOR = "tor"
    P2P = "p2p"
    RELAY = "relay"


class TransportLayer:
    """
    Транспортный фасад FIEP:
      - NAT
      - локальный relay
      - relay-клиент
      - WebRTC
      - UDP hole-punching
      - DHT
      - Tor
      - Router
    """

    def __init__(self, config, identity, password_provider):
        self.config = config
        self.identity = identity
        self.password_provider = password_provider

        self.mode = NetworkMode.RELAY
        self.running = False

        self.incoming_handler: Optional[Callable[[str, bytes], None]] = None

        # NAT
        self.nat = NatManager()

        # Tor
        self.tor: Optional[TorManager] = None
        self.onion_address: Optional[str] = None

        # Relay
        self.relay: Optional[DynamicRelayNode] = None
        self.relay_client: Optional[RelayClient] = None

        # WebRTC
        self.webrtc: Optional[WebRTCIntegration] = None

        # UDP hole-punch
        self.udp: Optional[UDPPuncher] = None
        self.udp_peers: Dict[str, Tuple[str, int]] = {}
        self.udp_punched: Dict[str, bool] = {}

        # DHT
        self.dht: Optional[DHTClient] = None

        # Router
        self.router: Optional[Router] = None

        # Central relay
        self.central_relay_host = getattr(config, "CENTRAL_RELAY_HOST", None)
        self.central_relay_port = getattr(config, "CENTRAL_RELAY_PORT", None)

    # ---------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------

    def start(self, mode: str):
        if self.running:
            logger.info("Transport already running")
            return

        self.mode = mode
        logger.info("Transport start, mode=%s", mode)

        # 1) Локальный relay-сервер
        self.relay = DynamicRelayNode(
            fingerprint=self.identity.fingerprint,
            peer_id=str(self.identity.peer_id),
            dht=None,
            central_host=self.central_relay_host,
            central_port=self.central_relay_port,
        )
        self.relay.add_handler(self._on_relay_envelope)
        self.relay.start()

        relay_port = self.relay.port

        # 2) NAT
        self.nat.setup_for_port(relay_port)

        if self.nat.external_ip:
            self.relay.update_public_ip(self.nat.external_ip)

        # 3) Tor (если включён)
        if mode == NetworkMode.TOR:
            try:
                self.tor = TorManager(relay_port)
                if self.tor.start():
                    self.onion_address = self.tor.get_onion_address()
                    logger.info("Tor onion: %s", self.onion_address)
            except Exception as e:
                logger.error("Tor start error: %s", e)

        # 4) UDP hole-puncher
        self.udp = UDPPuncher()
        self.udp.start(self._on_udp_datagram)

        # 5) DHT-клиент
        self.dht = DHTClient(
            fingerprint=self.identity.fingerprint,
            bootstrap_nodes=self._get_bootstrap_nodes()
        )
        self.dht.bootstrap()

        # Публикуем себя в DHT
        if self.dht:
            self.dht.publish_self(
                address=self.nat.external_ip or self.nat.local_ip,
                port=relay_port,
                udp_port=self.udp.external_port if self.udp else None
            )

        # 6) Relay-клиент
        self.relay_client = RelayClient(
            fingerprint=self.identity.fingerprint,
            local_ip=self.nat.local_ip,
            external_ip=self.nat.external_ip,
            relay_port=relay_port,
            get_bootstrap_nodes=self._get_bootstrap_nodes,
            get_fallback_relays=self._get_fallback_relays_from_dag,
            on_message=self._on_relay_envelope,
            on_dag=self._on_relay_dag,
            central_host=self.central_relay_host,
            central_port=self.central_relay_port,
        )
        self.relay_client.start()

        # 7) WebRTC-интеграция
        self.webrtc = WebRTCIntegration(
            fingerprint=self.identity.fingerprint,
            signaling_send=self._send_webrtc_signal,
            on_message=self._on_webrtc_message,
            dag_lookup_all=self._dag_nodes,
        )

        # 8) Router
        self.router = Router(
            fingerprint=self.identity.fingerprint,
            webrtc_send=self._webrtc_send,
            udp_send=self._udp_send,
            udp_available=self._udp_available,
            relay_send=self._relay_send,
            dag_lookup=self._dag_lookup,
            tor_socket_factory=self._tor_socket_factory,
            mode=self.mode,
        )

        # 9) Отправляем свою UDP-инфу через relay
        self._announce_udp_info()

        self.running = True
        logger.info("Transport started successfully")

    def stop(self):
        if not self.running:
            return

        logger.info("Transport stop")

        if self.relay_client:
            self.relay_client.stop()

        if self.relay:
            self.relay.stop()

        if self.webrtc:
            self.webrtc.shutdown()

        if self.tor:
            self.tor.stop()

        if self.udp:
            self.udp.stop()

        self.nat.cleanup()

        self.running = False

    # ---------------------------------------------------------
    # ROUTER HELPERS
    # ---------------------------------------------------------

    def _webrtc_send(self, fp: str, ciphertext: bytes) -> bool:
        if not self.webrtc:
            return False
        return self.webrtc.webrtc.send(fp, ciphertext)

    def _relay_send(self, env: Dict[str, Any]) -> bool:
        if not self.relay:
            return False
        return self.relay.send_envelope(env)

    def _dag_lookup(self, fp: str):
        # 1) DAG
        if self.relay:
            node = self.relay.dag.nodes.get(fp)
            if node:
                return node

        # 2) DHT fallback
        if self.dht:
            info = self.dht.lookup(fp)
            if info and self.relay:
                self.relay.dag.update_node(fp, {
                    "address": info.get("address"),
                    "port": info.get("port"),
                    "udp_ip": info.get("address"),
                    "udp_port": info.get("udp_port"),
                })
                return self.relay.dag.nodes.get(fp)

        return None

    def _dag_nodes(self):
        if not self.relay:
            return {}
        return self.relay.dag.nodes

    def _tor_socket_factory(self):
        if self.tor and self.tor.is_running:
            return self.tor.create_tor_socket()
        return None

    # ---------------------------------------------------------
    # UDP HELPERS
    # ---------------------------------------------------------

    def _udp_available(self, fp: str) -> bool:
        return fp in self.udp_peers and self.udp is not None

    def _udp_send(self, fp: str, ciphertext: bytes) -> bool:
        if not self.udp:
            return False
        if fp not in self.udp_peers:
            return False

        ip, port = self.udp_peers[fp]

        # Первый раз пробиваем NAT
        if not self.udp_punched.get(fp):
            self.udp.punch(ip, port)
            self.udp_punched[fp] = True

        return self.udp.send(ciphertext, ip, port)

    def _on_udp_datagram(self, data: bytes, addr: Tuple[str, int]):
        sender_fp = None
        for fp, (ip, port) in self.udp_peers.items():
            if ip == addr[0] and port == addr[1]:
                sender_fp = fp
                break

        if not sender_fp:
            return

        if self.incoming_handler:
            self.incoming_handler(sender_fp, data)

    def _announce_udp_info(self):
        if not self.udp or not self.relay:
            return
        if not self.udp.external_ip or not self.udp.external_port:
            return

        env = {
            "type": "udp-info",
            "from": self.identity.fingerprint,
            "external_ip": self.udp.external_ip,
            "external_port": self.udp.external_port,
            "timestamp": int(time.time()),
        }
        self.relay.send_envelope(env)

        # Публикуем в DHT
        if self.dht:
            self.dht.store(
                key=f"udp:{self.identity.fingerprint}",
                value={
                    "ip": self.udp.external_ip,
                    "port": self.udp.external_port,
                    "timestamp": int(time.time())
                }
            )

    # ---------------------------------------------------------
    # WEBRTC SIGNALING
    # ---------------------------------------------------------

    def _send_webrtc_signal(self, env: Dict[str, Any]):
        if self.relay:
            self.relay.send_envelope(env)

    def _on_webrtc_message(self, sender_fp: str, data: bytes):
        if self.incoming_handler:
            self.incoming_handler(sender_fp, data)

    # ---------------------------------------------------------
    # RELAY EVENTS
    # ---------------------------------------------------------

    def _on_relay_envelope(self, env: Dict[str, Any]):
        etype = env.get("type")

        # UDP-INFO
        if etype == "udp-info":
            sender_fp = env.get("from")
            ip = env.get("external_ip")
            port = env.get("external_port")

            if sender_fp and ip and port:
                self.udp_peers[sender_fp] = (ip, int(port))

                if self.relay:
                    self.relay.dag.update_node(sender_fp, {
                        "udp_ip": ip,
                        "udp_port": int(port)
                    })

                # Публикуем в DHT
                if self.dht:
                    self.dht.store(
                        key=f"udp:{sender_fp}",
                        value={"ip": ip, "port": int(port), "timestamp": int(time.time())}
                    )

            return

        # WebRTC signaling
        if etype == "message" and env.get("webrtc"):
            sender_fp = env.get("from")
            payload_b64 = env.get("payload")

            try:
                raw = base64.b64decode(payload_b64)
                signal = json.loads(raw.decode("utf-8"))
                if self.webrtc:
                    self.webrtc.handle_signal(sender_fp, signal)
            except Exception as e:
                logger.error("WebRTC signaling parse error: %s", e)
            return

        # Обычное сообщение
        if etype == "message":
            sender_fp = env.get("from")
            payload_b64 = env.get("payload")

            try:
                ciphertext = base64.b64decode(payload_b64)
            except Exception:
                return

            if self.incoming_handler:
                self.incoming_handler(sender_fp, ciphertext)

    def _on_relay_dag(self, env: Dict[str, Any]):
        if self.relay:
            self.relay._handle_dag(env)
        if self.webrtc:
            self.webrtc.auto_connect()

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def register_incoming_handler(self, handler: Callable[[str, bytes], None]):
        self.incoming_handler = handler

    def send_encrypted(self, recipient_fp: str, ciphertext: bytes) -> bool:
        return self.router.send(recipient_fp, ciphertext)

    # ---------------------------------------------------------
    # BOOTSTRAP HELPERS
    # ---------------------------------------------------------

    def _get_bootstrap_nodes(self):
        res = []
        for item in getattr(self.config, "BOOTSTRAP_NODES", []):
            try:
                host, port_str = item.split(":")
                res.append((host, int(port_str)))
            except Exception:
                continue
        return res

    def _get_fallback_relays_from_dag(self):
        if not self.relay:
            return []
        nodes = []
        for fp, node in self.relay.dag.nodes.items():
            if fp == self.identity.fingerprint:
                continue
            if getattr(node, "address", None) and getattr(node, "port", None):
                if getattr(node, "address_type", "ip") == "ip":
                    nodes.append((node.address, node.port))
        return nodes

    # ---------------------------------------------------------
    # DIAGNOSTICS
    # ---------------------------------------------------------

    def get_network_diagnostics(self):
        return {
            "mode": self.mode,
            "local_ip": self.nat.local_ip,
            "external_ip": self.nat.external_ip,
            "nat_type": self.nat.nat_type,
            "upnp": self.nat.upnp_status,
            "pcp": self.nat.pcp_status,
            "natpmp": self.nat.natpmp_status,
            "tor": self.tor is not None,
            "onion": self.onion_address,
            "relay_ip": self.relay.public_ip if self.relay else None,
            "relay_port": self.relay.port if self.relay else None,
            "dag_nodes": len(self.relay.dag.nodes) if self.relay else 0,
            "udp_external_ip": self.udp.external_ip if self.udp else None,
            "udp_external_port": self.udp.external_port if self.udp else None,
            "udp_peers": len(self.udp_peers),
        }

    def is_contact_online(self, fingerprint: str) -> bool:
        node = self._dag_lookup(fingerprint)
        return bool(node and getattr(node, "address", None) and getattr(node, "port", None))
