# FIEP/app/messenger.py

import json
import time
from typing import Callable, Optional

from FIEP.core.identity import Identity
from FIEP.network.transport import TransportLayer
from FIEP.app.message_model import InnerMessage, SignedMessage
from FIEP.app.contacts import ContactStore
from FIEP.app.storage import MessageStorage


class Messenger:
    def __init__(self,
                 identity: IdentityManager,
                 transport: TransportLayer,
                 contacts: ContactStore,
                 storage: MessageStorage):
        self.id = identity
        self.transport = transport
        self.contacts = contacts
        self.storage = storage

        self._on_message_cb: Optional[Callable[[str, InnerMessage], None]] = None

        # регистрируемся в транспорте
        self.transport.register_incoming_handler(self._on_incoming_ciphertext)

    # -----------------------------------------------------
    # Публичный API
    # -----------------------------------------------------

    def on_message(self, cb: Callable[[str, InnerMessage], None]):
        self._on_message_cb = cb

    def send_text(self, peer_fp: str, text: str):
        contact = self.contacts.get(peer_fp)
        if not contact:
            raise RuntimeError(f"Неизвестный контакт: {peer_fp}")

        msg = InnerMessage(
            type="text",
            text=text,
            timestamp=int(time.time()),
        )

        # 1) сериализуем тело
        body_dict = msg.to_dict()
        body_json = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        # 2) подпись Ed25519 по открытому тексту
        signature = self.id.sign(body_json)
        signed = SignedMessage(body=msg, signature=signature)
        signed_bytes = signed.to_bytes()

        # 3) шифрование для X25519-ключа собеседника
        enc = self.id.encrypt_for(contact.x25519_public, signed_bytes)

        packet = {
            "version": 1,
            "from": self.id.fingerprint,
            "to": peer_fp,
            "nonce": enc["nonce"],
            "ciphertext": enc["ciphertext"],
        }
        packet_bytes = json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        # 4) отправка через транспорт
        self.transport.send_encrypted(peer_fp, packet_bytes)

        # 5) запись в историю
        self.storage.save_outgoing(peer_fp, msg)

    def get_history(self, peer_fp: str):
        return self.storage.load_history(peer_fp)

    # -----------------------------------------------------
    # Входящие данные от транспорта
    # -----------------------------------------------------

    def _on_incoming_ciphertext(self, sender_fp: str, data: bytes):
        try:
            packet = json.loads(data.decode("utf-8"))
            if packet.get("version") != 1:
                return

            contact = self.contacts.get(sender_fp)
            if not contact:
                # можно пометить как "неизвестный отправитель"
                return

            enc = {
                "nonce": packet["nonce"],
                "ciphertext": packet["ciphertext"],
            }

            # 1) расшифровка
            signed_bytes = self.id.decrypt_from(contact.x25519_public, enc)

            # 2) парсинг SignedMessage
            signed = SignedMessage.from_bytes(signed_bytes)

            # 3) проверка подписи
            body_dict = signed.body.to_dict()
            body_json = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

            ok = IdentityManager.verify(
                data=body_json,
                signature=signed.signature,
                pubkey=contact.ed25519_public,
            )
            if not ok:
                # подпись не сошлась — можно логировать/дропать
                return

            msg = signed.body

            # 4) запись в историю
            self.storage.save_incoming(sender_fp, msg)

            # 5) уведомление верхнего слоя (UI)
            if self._on_message_cb:
                self._on_message_cb(sender_fp, msg)

        except Exception as e:
            # здесь лучше использовать твой net_logger, но для каркаса оставлю print
            print("Messenger incoming error:", e)
