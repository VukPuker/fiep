# nat.py
# NAT / IP / порт-маппинг для FIEP: local IP, external IP, UPnP, PCP, NAT-PMP.

import socket
import urllib.request
from typing import Optional, List, Tuple

from FIEP.network.net_logging import get_network_logger

logger = get_network_logger("FIEP.network.nat")

try:
    import miniupnpc
except ImportError:
    miniupnpc = None

try:
    from pcp import PCPClient
except ImportError:
    PCPClient = None

try:
    from natpmp import NATPMP
except ImportError:
    NATPMP = None


class NatManager:
    def __init__(self):
        self.local_ip: Optional[str] = None
        self.external_ip: Optional[str] = None
        self.nat_type: str = "unknown"

        self._upnp = None
        self._upnp_mapped: List[Tuple[int, str]] = []

        self.upnp_status: bool = False
        self.pcp_status: bool = False
        self.natpmp_status: bool = False

    # -----------------------------------------------------
    # IP DETECT
    # -----------------------------------------------------

    def detect_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.local_ip = "127.0.0.1"
        logger.info("Local IP detected: %s", self.local_ip)

    def _detect_external_ip_http(self) -> Optional[str]:
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
                return resp.read().decode().strip()
        except Exception:
            return None

    # -----------------------------------------------------
    # UPNP / PCP / NATPMP
    # -----------------------------------------------------

    def _init_upnp(self) -> bool:
        if miniupnpc is None:
            logger.info("miniupnpc not installed, skipping UPnP")
            return False
        try:
            u = miniupnpc.UPnP()
            u.discoverdelay = 200
            n = u.discover()
            logger.info("UPnP discover: found %s devices", n)
            u.selectigd()
            self._upnp = u
            logger.info("UPnP IGD selected: %s", self._upnp.lanaddr)
            return True
        except Exception as e:
            logger.warning("UPnP init failed: %s", e)
            self._upnp = None
            return False

    def _upnp_add_mapping(self, external_port: int, internal_port: int, proto: str, desc: str) -> bool:
        if not self._upnp:
            return False
        try:
            self._upnp.addportmapping(
                external_port, proto,
                self._upnp.lanaddr, internal_port,
                desc, ""
            )
            self._upnp_mapped.append((external_port, proto))
            logger.info("UPnP: mapped %s %s -> %s (%s)", proto, external_port, internal_port, desc)
            return True
        except Exception as e:
            logger.warning("UPnP add mapping failed (%s %s): %s", proto, external_port, e)
            return False

    def _upnp_remove_all(self):
        if not self._upnp:
            return
        for port, proto in self._upnp_mapped:
            try:
                self._upnp.deleteportmapping(port, proto)
                logger.info("UPnP: removed mapping %s %s", proto, port)
            except Exception as e:
                logger.warning("UPnP remove mapping failed (%s %s): %s", proto, port, e)
        self._upnp_mapped.clear()

    def _try_pcp_mapping(self, port: int, proto: str) -> bool:
        if PCPClient is None:
            logger.info("PCP not installed")
            return False
        try:
            client = PCPClient()
            client.map(port, protocol=proto.lower())
            logger.info("PCP: mapped %s %s", proto, port)
            return True
        except Exception as e:
            logger.warning("PCP mapping failed: %s", e)
            return False

    def _try_natpmp_mapping(self, port: int, proto: str) -> bool:
        if NATPMP is None:
            logger.info("NAT-PMP not installed")
            return False
        try:
            client = NATPMP()
            if proto.upper() == "TCP":
                client.map_tcp(port, lifetime=3600)
            else:
                client.map_udp(port, lifetime=3600)
            logger.info("NAT-PMP: mapped %s %s", proto, port)
            return True
        except Exception as e:
            logger.warning("NAT-PMP mapping failed: %s", e)
            return False

    # -----------------------------------------------------
    # NAT TYPE
    # -----------------------------------------------------

    def _detect_nat_type(self):
        if not self.external_ip:
            self.nat_type = "unknown"
            return

        cgnat_blocks = [
            ("100.64.0.0", "100.127.255.255"),
        ]

        def ip_to_int(ip: str) -> int:
            parts = list(map(int, ip.split(".")))
            return (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]

        ext = ip_to_int(self.external_ip)

        for start, end in cgnat_blocks:
            if ip_to_int(start) <= ext <= ip_to_int(end):
                self.nat_type = "cgnat"
                return

        self.nat_type = "public"

    # -----------------------------------------------------
    # HIGH-LEVEL API
    # -----------------------------------------------------

    def setup_for_port(self, port: int, proto: str = "TCP"):
        """
        Полный цикл:
        - определяем local_ip
        - пробуем UPnP → PCP → NAT-PMP
        - определяем external_ip
        - определяем nat_type
        """
        self.detect_local_ip()

        # UPnP
        if self._init_upnp():
            if self._upnp_add_mapping(port, port, proto.upper(), "FIEP"):
                self.upnp_status = True
                try:
                    self.external_ip = self._upnp.externalipaddress()
                except Exception:
                    self.external_ip = None
                logger.info("Cascade: UPnP success → direct mode")
            else:
                self.upnp_status = False
        else:
            self.upnp_status = False

        # PCP
        if not self.upnp_status:
            logger.info("Cascade: UPnP failed → trying PCP")
            if self._try_pcp_mapping(port, proto.upper()):
                self.pcp_status = True
            else:
                self.pcp_status = False

        # NAT-PMP
        if not self.upnp_status and not self.pcp_status:
            logger.info("Cascade: PCP failed → trying NAT-PMP")
            if self._try_natpmp_mapping(port, proto.upper()):
                self.natpmp_status = True
            else:
                self.natpmp_status = False

        # External IP (если не получили от UPnP)
        if not self.external_ip:
            self.external_ip = self._detect_external_ip_http()

        self._detect_nat_type()

        logger.info(
            "NAT setup done: local=%s external=%s nat_type=%s upnp=%s pcp=%s natpmp=%s",
            self.local_ip,
            self.external_ip,
            self.nat_type,
            self.upnp_status,
            self.pcp_status,
            self.natpmp_status,
        )

    def cleanup(self):
        """
        Удаляет все UPnP-маппинги.
        """
        self._upnp_remove_all()

    def get_diagnostics(self):
        return {
            "local_ip": self.local_ip,
            "external_ip": self.external_ip,
            "nat_type": self.nat_type,
            "upnp": self.upnp_status,
            "pcp": self.pcp_status,
            "natpmp": self.natpmp_status,
        }
