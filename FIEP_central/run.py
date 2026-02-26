# run.py
# Автономный запуск центрального relay-сервера FIEP.
# Добавляет relay в DAG, запускает STUN/IP-детектор, DDNS, мониторинг.

import asyncio
import time
import threading

from relay_server import main as relay_main
from stun_detect import StunDetector
from dag_manager import DAGManager
from centrallogging import CentralLogger
from ddns_update import get_public_ip
from config import PORT, DDNS_ENABLED, STUN_CHECK_INTERVAL, LOG_LEVEL

logger = CentralLogger("main", level=LOG_LEVEL)


def print_banner():
    print("\n" + "=" * 60)
    print("        FIEP CENTRAL RELAY — AUTONOMOUS MODE")
    print("=" * 60)
    print(f"  • Relay port: {PORT}")
    print(f"  • DDNS enabled: {DDNS_ENABLED}")
    print(f"  • STUN/IP check interval: {STUN_CHECK_INTERVAL}s")
    print("=" * 60 + "\n")


def print_status(detector: StunDetector, dag: DAGManager):
    print("\n" + "-" * 60)
    print(" CENTRAL RELAY STATUS")
    print("-" * 60)

    wan_ip = detector.current_ip or "detecting..."
    print(f"  WAN IP: {wan_ip}")
    print(f"  Relay port: {PORT}")

    nodes = dag.get_all()
    white = sum(1 for n in nodes.values() if n.get("node_type") == "white")
    gray = sum(1 for n in nodes.values() if n.get("node_type") == "gray")

    print(f"  Nodes total: {len(nodes)}")
    print(f"    • White IP nodes: {white}")
    print(f"    • Gray/NAT nodes: {gray}")

    webrtc_count = sum(1 for n in nodes.values() if n.get("webrtc"))
    print(f"  WebRTC active: {webrtc_count}")

    udp_count = sum(1 for n in nodes.values() if n.get("udp_ip"))
    print(f"  UDP nodes: {udp_count}")

    print("-" * 60 + "\n")


def start_status_printer(detector: StunDetector, dag: DAGManager):
    def loop():
        while True:
            try:
                print_status(detector, dag)
            except Exception as e:
                logger.error(f"Status printer error: {e}")
            time.sleep(10)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


def start_stun(detector: StunDetector):
    detector.start_background(interval=STUN_CHECK_INTERVAL)


if __name__ == "__main__":
    print_banner()

    # Инициализация DAG
    dag = DAGManager()

    # Определяем WAN-IP (через ipify)
    wan_ip = get_public_ip() or "0.0.0.0"

    # Регистрируем центральный relay как узел DAG
    dag.update_node("central-relay", {
        "address": wan_ip,
        "port": PORT,
        "local_ip": "127.0.0.1",
        "supports_webrtc": False,
        "relay": True
    })

    logger.info(f"Central relay registered in DAG as central-relay ({wan_ip}:{PORT})")

    # STUN/IP-детектор
    detector = StunDetector()
    start_stun(detector)

    # Периодический вывод статуса
    start_status_printer(detector, dag)

    # Запуск relay-сервера
    asyncio.run(relay_main())
