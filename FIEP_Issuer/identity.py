import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def generate_identity():
    """
    Генерирует Ed25519 identity:

    - public_key: raw 32 байта, base64 (строка)
    - private_key: raw 32 байта, base64 (строка)
    - fingerprint: SHA-256(public_key_raw), hex (строка)
    - peer_id: base32(public_key_raw) без '=' (строка)
    """
    # 1. Генерация ключей
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # 2. Сырые байты ключей
    priv_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # 3. base64-представление
    priv_b64 = base64.b64encode(priv_raw).decode("ascii")
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")

    # 4. fingerprint = SHA-256(public_key_raw), hex
    fingerprint = hashlib.sha256(pub_raw).hexdigest()

    # 5. peer_id = base32(public_key_raw) без '='
    peer_id = base64.b32encode(pub_raw).decode("ascii").rstrip("=")

    return {
        "public_key": pub_b64,
        "private_key": priv_b64,
        "fingerprint": fingerprint,
        "peer_id": peer_id,
    }
