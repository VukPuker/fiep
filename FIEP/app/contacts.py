# FIEP/app/contacts.py

import json
import os
import base64
from dataclasses import dataclass
from typing import Optional, Dict


CONTACTS_FILE = "contacts.json"


@dataclass
class Contact:
    fingerprint: str
    nickname: Optional[str]
    ed25519_public: bytes
    x25519_public: bytes

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "nickname": self.nickname,
            "ed25519_public": base64.b64encode(self.ed25519_public).decode(),
            "x25519_public": base64.b64encode(self.x25519_public).decode(),
        }

    @staticmethod
    def from_dict(d: dict) -> "Contact":
        return Contact(
            fingerprint=d["fingerprint"],
            nickname=d.get("nickname"),
            ed25519_public=base64.b64decode(d["ed25519_public"]),
            x25519_public=base64.b64decode(d["x25519_public"]),
        )


class ContactStore:
    def __init__(self, base_path: str = "data"):
        self.base_path = base_path
        self.path = os.path.join(base_path, CONTACTS_FILE)
        os.makedirs(base_path, exist_ok=True)
        self._contacts: Dict[str, Contact] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for fp, c in raw.items():
            self._contacts[fp] = Contact.from_dict(c)

    def _save(self):
        data = {fp: c.to_dict() for fp, c in self._contacts.items()}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_or_update(self, contact: Contact):
        self._contacts[contact.fingerprint] = contact
        self._save()

    def get(self, fingerprint: str) -> Optional[Contact]:
        return self._contacts.get(fingerprint)

    def all(self):
        return list(self._contacts.values())
