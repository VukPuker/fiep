import os
import base64
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------
# Base32 activation key generation
# ---------------------------------------------------------

def generate_activation_key():
    """
    Generates a 256-bit activation key and returns it as a base32 string.
    """
    raw = os.urandom(32)  # 256 bits
    b32 = base64.b32encode(raw).decode("ascii").replace("=", "")
    return b32, raw


# ---------------------------------------------------------
# KDF: Argon2id
# ---------------------------------------------------------

def kdf_argon2id(secret: bytes, salt: bytes, time_cost: int, memory_cost: int, parallelism: int = 1):
    """
    Derives a 256-bit key using Argon2id.
    """
    return hash_secret_raw(
        secret,
        salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID
    )


# ---------------------------------------------------------
# AES-256-GCM encryption/decryption
# ---------------------------------------------------------

def aes_gcm_encrypt(key: bytes, plaintext: bytes):
    """
    Encrypts plaintext using AES-256-GCM.
    Returns (nonce, ciphertext).
    """
    nonce = os.urandom(12)  # 96-bit nonce
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, plaintext, None)
    return nonce, ciphertext


def aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes):
    """
    Decrypts AES-256-GCM ciphertext.
    """
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------
# Helpers for base64 encoding/decoding
# ---------------------------------------------------------

def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))
