# test_network.py
#
# Интеграционный тест сетевого стека FIEP (изолированный от core).
# Проверяет:
#   - запуск TransportLayer
#   - TCP relay
#   - UDP hole-punching
#   - WebRTC
#   - fallback Router
#   - DHT publish/lookup

import time
import threading

from FIEP.network.transport import TransportLayer, NetworkMode
from FIEP.network.config import config


# ---------------------------------------------------------
# DUMMY IDENTITY (замена core.identity)
# ---------------------------------------------------------

class DummyIdentity:
    def __init__(self, name: str):
        self.name = name
        self.peer_id = name
        self.fingerprint = name  # строка, чтобы не путать с байтами
        self.public_key = b"dummy-public"
        self.private_key = b"dummy-private"

    def sign(self, data: bytes) -> bytes:
        return b"sig-" + data

    def verify(self, data: bytes, signature: bytes) -> bool:
        return signature == b"sig-" + data

    def encrypt_for(self, peer_fp: str, data: bytes) -> bytes:
        return b"enc-" + data

    def decrypt(self, data: bytes) -> bytes:
        if data.startswith(b"enc-"):
            return data[4:]
        return data


# ---------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ---------------------------------------------------------

def wait_for(condition, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------
# ТЕСТЫ
# ---------------------------------------------------------

def test_startup(t1, t2):
    print("\n[1] Тест запуска TransportLayer...")

    assert t1.running
    assert t2.running

    print("  OK: оба узла запущены")


def test_tcp_direct(t1, t2, fp1, fp2):
    print("\n[2] Тест TCP direct relay...")

    received = []

    def handler(fp, data):
        received.append((fp, data))

    t2.register_incoming_handler(handler)
    t1.send_encrypted(fp2, b"tcp-test")

    assert wait_for(lambda: received, 5), "TCP direct не доставил сообщение"
    print("  OK: TCP direct работает")


def test_udp(t1, t2, fp1, fp2):
    print("\n[3] Тест UDP hole-punching...")

    received = []

    def handler(fp, data):
        received.append((fp, data))

    t2.register_incoming_handler(handler)
    t1._udp_send(fp2, b"udp-test")

    assert wait_for(lambda: received, 5), "UDP не доставил сообщение"
    print("  OK: UDP работает")


def test_webrtc(t1, t2, fp1, fp2):
    print("\n[4] Тест WebRTC...")

    received = []

    def handler(fp, data):
        received.append((fp, data))

    t2.register_incoming_handler(handler)

    t1.webrtc.connect(fp2)
    time.sleep(3)

    t1._webrtc_send(fp2, b"webrtc-test")

    assert wait_for(lambda: received, 5), "WebRTC не доставил сообщение"
    print("  OK: WebRTC работает")


def test_dht(t1, t2, fp1, fp2):
    print("\n[5] Тест DHT...")

    t1.dht.publish_self("127.0.0.1", t1.relay.port)
    time.sleep(1)

    info = t2.dht.lookup(fp1)
    assert info, "DHT lookup не вернул данные"

    print("  OK: DHT работает:", info)


def test_router_fallbacks(t1, t2, fp1, fp2):
    print("\n[6] Тест fallback маршрутизации Router...")

    received = []

    def handler(fp, data):
        received.append((fp, data))

    t2.register_incoming_handler(handler)
    t1.send_encrypted(fp2, b"router-test")

    assert wait_for(lambda: received, 5), "Router не доставил сообщение"
    print("  OK: Router работает")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":
    print("=== FIEP NETWORK TEST SUITE ===")

    # создаём две dummy-identity
    id1 = DummyIdentity("test1")
    id2 = DummyIdentity("test2")

    fp1 = id1.fingerprint
    fp2 = id2.fingerprint

    # создаём два TransportLayer
    t1 = TransportLayer(config, id1, password_provider=lambda: "123")
    t2 = TransportLayer(config, id2, password_provider=lambda: "123")

    # запускаем
    t1.start(NetworkMode.RELAY)

    config.CENTRAL_RELAY_HOST = "127.0.0.1"
    config.CENTRAL_RELAY_PORT = t1.relay.port

    t2.start(NetworkMode.P2P)


    time.sleep(2)

    # тесты
    test_startup(t1, t2)
    test_tcp_direct(t1, t2, fp1, fp2)
    test_udp(t1, t2, fp1, fp2)
    test_webrtc(t1, t2, fp1, fp2)
    test_dht(t1, t2, fp1, fp2)
    test_router_fallbacks(t1, t2, fp1, fp2)

    print("\n=== ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО ===")
