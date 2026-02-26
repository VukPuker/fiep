# ddns_update.py
# Обновление IP через DuckDNS с определением WAN-IP через api.ipify.org

import json
import urllib.request
from urllib.error import URLError
from centrallogging import CentralLogger

logger = CentralLogger("ddns_update")

DDNS_CFG_FILE = "ddns_cfg.json"


def load_ddns_cfg():
    try:
        with open(DDNS_CFG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ddns_cfg.json: {e}")
        return None


def get_public_ip() -> str | None:
    """Определяет WAN-IP через api.ipify.org"""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            ip = response.read().decode("utf-8").strip()
            return ip
    except Exception as e:
        logger.error(f"Failed to get public IP from ipify: {e}")
        return None


def update_ddns():
    """
    Определяет WAN-IP через ipify и обновляет DuckDNS.
    """
    cfg = load_ddns_cfg()
    if not cfg:
        logger.error("DDNS config missing, skipping update")
        return

    domain = cfg.get("domain")
    token = cfg.get("token")

    if not domain or not token:
        logger.error("DDNS config invalid: missing domain or token")
        return

    ip = get_public_ip()
    if not ip:
        logger.error("Cannot update DDNS: public IP unknown")
        return

    url = f"https://www.duckdns.org/update?domains={domain}&token={token}&ip={ip}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            result = response.read().decode("utf-8").strip()

        if result == "OK":
            logger.info(f"DDNS updated: {domain}.duckdns.org → {ip}")
        else:
            logger.warning(f"DDNS update returned unexpected result: {result}")

    except URLError as e:
        logger.error(f"DDNS update failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected DDNS error: {e}")
