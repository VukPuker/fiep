# FIEP/app/message_model.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
import json
import base64


@dataclass
class InnerMessage:
    type: str
    text: Optional[str] = None
    timestamp: int = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "text": self.text,
            "timestamp": self.timestamp or int(time.time()),
            "meta": self.meta or {},
        }

    @staticmethod
    def from_dict(d: dict) -> "InnerMessage":
        return InnerMessage(
            type=d["type"],
            text=d.get("text"),
            timestamp=d.get("timestamp"),
            meta=d.get("meta") or {},
        )


@dataclass
class SignedMessage:
    body: InnerMessage
    signature: bytes  # Ed25519

    def to_bytes(self) -> bytes:
        body_dict = self.body.to_dict()
        body_json = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return json.dumps({
            "body": base64.b64encode(body_json).decode(),
            "signature": base64.b64encode(self.signature).decode(),
        }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> "SignedMessage":
        obj = json.loads(data.decode("utf-8"))
        body_json = base64.b64decode(obj["body"])
        sig = base64.b64decode(obj["signature"])
        body = InnerMessage.from_dict(json.loads(body_json.decode("utf-8")))
        return SignedMessage(body=body, signature=sig)
