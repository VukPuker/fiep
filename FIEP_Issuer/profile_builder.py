import os
import json
import time

from crypto import (
    generate_activation_key,
    kdf_argon2id,
    aes_gcm_encrypt,
    b64e,
)


# ---------------------------------------------------------
# Параметры KDF для activation_key → storage_key
# ---------------------------------------------------------

ACTIVATION_KDF_PARAMS = {
    "time_cost": 3,
    "memory_cost": 64 * 1024,  # 64 MB
    "parallelism": 1,
}


def build_profile(identity_public: str,
                  identity_private: str,
                  fingerprint: str,
                  peer_id: str,
                  extra_config: dict | None = None) -> dict:
    """
    Собирает структуру профиля (ещё НЕ зашифрованную).
    """
    if extra_config is None:
        extra_config = {}

    profile = {
        "version": 1,
        "identity": {
            "public_key": identity_public,
            "private_key": identity_private,
            "fingerprint": fingerprint,
            "peer_id": peer_id,
        },
        "config": {
            "nickname": None,
            "settings": {},
            "network": {},
            **extra_config,
        },
        "state": {
            "created_at": int(time.time()),
        },
    }
    return profile


def encrypt_profile_with_activation(profile: dict):
    """
    1) Генерирует activation_key (base32 + raw).
    2) Генерирует соль для KDF.
    3) Вычисляет storage_key через Argon2id.
    4) Шифрует профиль (JSON) через AES-GCM.
    5) Возвращает:
       - activation_key_b32 (строка для файла activation.key),
       - profile_enc (dict для записи в profile.enc),
       - storage_key (bytes) — пригодится для keycache.
    """
    # 1. activation key
    activation_b32, activation_raw = generate_activation_key()

    # 2. соль для KDF
    kdf_salt = os.urandom(16)

    # 3. storage_key
    storage_key = kdf_argon2id(
        secret=activation_raw,
        salt=kdf_salt,
        **ACTIVATION_KDF_PARAMS,
    )

    # 4. сериализация профиля
    profile_json = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # 5. шифрование AES-GCM
    nonce, ciphertext = aes_gcm_encrypt(storage_key, profile_json)

    profile_enc = {
        "version": 1,
        "kdf": "argon2id",
        "kdf_salt": b64e(kdf_salt),
        "cipher": "aes-256-gcm",
        "nonce": b64e(nonce),
        "ciphertext": b64e(ciphertext),
    }

    return activation_b32, profile_enc, storage_key
