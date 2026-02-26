import os
import json
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ВАЖНО: crypto — часть пакета FIEP.core
from FIEP.core.crypto import b64d, kdf_argon2id


class Identity:
    """
    Клиент НЕ генерирует Ed25519 и fingerprint.
    Клиент ТОЛЬКО активирует профиль, созданный Issuer-ом.

    Issuer кладёт на флешку:
        - profile.enc
        - activation.key

    Клиент:
        - читает activation.key
        - читает profile.enc
        - делает Argon2id → storage_key
        - расшифровывает профиль
        - извлекает Ed25519 ключи и fingerprint
        - генерирует X25519
        - создаёт identity.json
        - удаляет activation.key и profile.enc
    """

    def __init__(self, base_path="data"):
        self.base_path = base_path
        self.identity_path = os.path.join(base_path, "identity.json")
        self.profile_enc_path = os.path.join(base_path, "profile.enc")
        self.activation_key_path = os.path.join(base_path, "activation.key")

        self.ed_private = None
        self.ed_public = None
        self.x_private = None
        self.x_public = None
        self.fingerprint = None
        self.peer_id = None

        os.makedirs(base_path, exist_ok=True)

    # ---------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ---------------------------------------------------------

    def load_or_activate(self):
        if os.path.exists(self.identity_path):
            self._load_identity()
            return

        if os.path.exists(self.profile_enc_path) and os.path.exists(self.activation_key_path):
            self._activate_profile()
            return

        raise RuntimeError(
            "Профиль не найден. Требуется activation.key и profile.enc, "
            "созданные через FIEP_Issuer."
        )

    # ---------------------------------------------------------
    # LOAD EXISTING IDENTITY
    # ---------------------------------------------------------

    def _load_identity(self):
        with open(self.identity_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._load_keys_from_dict(data)

    # ---------------------------------------------------------
    # ACTIVATE PROFILE FROM ISSUER
    # ---------------------------------------------------------

    def _activate_profile(self):
        # 1. Читаем activation.key
        with open(self.activation_key_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()

        if not lines or not lines[0].startswith("FIEP-ACT-"):
            raise RuntimeError("activation.key повреждён или неверного формата.")

        activation_b32 = lines[1].strip()
        activation_raw = base64.b32decode(activation_b32 + "====")

        # 2. Читаем profile.enc
        with open(self.profile_enc_path, "r", encoding="utf-8") as f:
            enc = json.load(f)

        kdf_salt = b64d(enc["kdf_salt"])
        nonce = b64d(enc["nonce"])
        ciphertext = b64d(enc["ciphertext"])

        # 3. KDF Argon2id → storage_key
        storage_key = kdf_argon2id(
            secret=activation_raw,
            salt=kdf_salt,
            time_cost=3,
            memory_cost=64 * 1024,
            parallelism=1,
        )

        # 4. Расшифровка AES-GCM
        aes = AESGCM(storage_key)
        profile_json = aes.decrypt(nonce, ciphertext, None)
        profile = json.loads(profile_json.decode("utf-8"))

        # 5. Извлекаем Ed25519 и fingerprint
        ident = profile["identity"]

        ed_priv_raw = base64.b64decode(ident["private_key"])
        ed_pub_raw = base64.b64decode(ident["public_key"])

        self.ed_private = Ed25519PrivateKey.from_private_bytes(ed_priv_raw)
        self.ed_public = Ed25519PublicKey.from_public_bytes(ed_pub_raw)
        self.fingerprint = ident["fingerprint"]
        self.peer_id = ident["peer_id"]

        # 6. Генерируем X25519
        self.x_private = X25519PrivateKey.generate()
        self.x_public = self.x_private.public_key()

        # 7. Создаём identity.json
        self._save_identity()

        # 8. Удаляем одноразовые файлы
        os.remove(self.activation_key_path)
        os.remove(self.profile_enc_path)

    # ---------------------------------------------------------
    # SAVE IDENTITY.JSON
    # ---------------------------------------------------------

    def _save_identity(self):
        data = {
            "fingerprint": self.fingerprint,
            "peer_id": self.peer_id,
            "ed25519_private": base64.b64encode(
                self.ed_private.private_bytes_raw()
            ).decode(),
            "ed25519_public": base64.b64encode(
                self.ed_public.public_bytes_raw()
            ).decode(),
            "x25519_private": base64.b64encode(
                self.x_private.private_bytes_raw()
            ).decode(),
            "x25519_public": base64.b64encode(
                self.x_public.public_bytes_raw()
            ).decode(),
        }

        with open(self.identity_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # ---------------------------------------------------------
    # LOAD KEYS FROM IDENTITY.JSON
    # ---------------------------------------------------------

    def _load_keys_from_dict(self, data):
        self.fingerprint = data["fingerprint"]
        self.peer_id = data["peer_id"]

        self.ed_private = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(data["ed25519_private"])
        )
        self.ed_public = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(data["ed25519_public"])
        )

        self.x_private = X25519PrivateKey.from_private_bytes(
            base64.b64decode(data["x25519_private"])
        )
        self.x_public = X25519PublicKey.from_public_bytes(
            base64.b64decode(data["x25519_public"])
        )

    # ---------------------------------------------------------
    # SIGN / VERIFY
    # ---------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        return self.ed_private.sign(data)

    @staticmethod
    def verify(data: bytes, signature: bytes, pubkey: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(pubkey).verify(signature, data)
            return True
        except Exception:
            return False

    # ---------------------------------------------------------
    # ENCRYPT / DECRYPT (X25519 + AES-GCM)
    # ---------------------------------------------------------

    def encrypt_for(self, peer_pubkey: bytes, plaintext: bytes) -> dict:
        peer = X25519PublicKey.from_public_bytes(peer_pubkey)
        shared = self.x_private.exchange(peer)

        aes = AESGCM(shared)
        nonce = os.urandom(12)
        ciphertext = aes.encrypt(nonce, plaintext, None)

        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()
        }

    def decrypt_from(self, peer_pubkey: bytes, encrypted: dict) -> bytes:
        peer = X25519PublicKey.from_public_bytes(peer_pubkey)
        shared = self.x_private.exchange(peer)

        aes = AESGCM(shared)
        nonce = base64.b64decode(encrypted["nonce"])
        ciphertext = base64.b64decode(encrypted["ciphertext"])

        return aes.decrypt(nonce, ciphertext, None)
