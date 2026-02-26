# FIEP/app/storage.py

import os
import json
from typing import List
from dataclasses import asdict

from FIEP.app.message_model import InnerMessage


class MessageStorage:
    """
    Простое файловое хранилище:
    data/history/<fingerprint>.jsonl
    Каждая строка — JSON: {direction, peer_fp, message_dict}
    """

    def __init__(self, base_path: str = "data"):
        self.base_path = base_path
        self.history_dir = os.path.join(base_path, "history")
        os.makedirs(self.history_dir, exist_ok=True)

    def _path_for_peer(self, peer_fp: str) -> str:
        return os.path.join(self.history_dir, f"{peer_fp}.jsonl")

    def save_outgoing(self, peer_fp: str, msg: InnerMessage):
        self._append("out", peer_fp, msg)

    def save_incoming(self, peer_fp: str, msg: InnerMessage):
        self._append("in", peer_fp, msg)

    def _append(self, direction: str, peer_fp: str, msg: InnerMessage):
        path = self._path_for_peer(peer_fp)
        rec = {
            "direction": direction,
            "peer": peer_fp,
            "message": msg.to_dict(),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def load_history(self, peer_fp: str) -> List[dict]:
        path = self._path_for_peer(peer_fp)
        if not os.path.exists(path):
            return []
        res = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    res.append(json.loads(line))
                except Exception:
                    continue
        return res
