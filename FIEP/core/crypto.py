import base64
from argon2.low_level import hash_secret_raw, Type


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def b64d(data: str) -> bytes:
    return base64.b64decode(data)


def kdf_argon2id(secret: bytes, salt: bytes, time_cost=3, memory_cost=64 * 1024, parallelism=1) -> bytes:
    """
    KDF Argon2id → 32‑байтный ключ.
    Совместим с Issuer.
    """
    return hash_secret_raw(
        secret=secret,
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID,
    )
