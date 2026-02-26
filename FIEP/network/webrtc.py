# webrtc.py
#
# Гибридный WebRTC-слой для FIEP:
# - WebRTCPeer: одна P2P-связь с конкретным fingerprint
# - WebRTCManager: управляет всеми WebRTCPeer, даёт TransportLayer простой API:
#       - connect_to(remote_fp)
#       - send(remote_fp, data: bytes)
#       - handle_signal(from_fp, signal: dict)
#
# Требует: pip install aiortc

import asyncio
import threading
from typing import Callable, Dict, Optional, Any, List

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCConfiguration,
    RTCIceServer,
)

from FIEP.network.net_logging import get_network_logger


logger = get_network_logger("FIEP.network.webrtc")


DEFAULT_STUN = [{"urls": "stun:stun.l.google.com:19302"}]


class WebRTCPeer:
    """
    Одна WebRTC-связь с конкретным удалённым fingerprint.
    Не знает ничего о relay/DAG — только о сигналинге и DataChannel.
    """

    def __init__(
        self,
        local_fp: str,
        remote_fp: str,
        loop: asyncio.AbstractEventLoop,
        signaling_send: Callable[[str, Dict[str, Any]], None],
        on_message: Callable[[str, bytes], None],
        ice_servers: Optional[List[Dict[str, str]]] = None,
    ):
        self.local_fp = local_fp
        self.remote_fp = remote_fp
        self.loop = loop
        self.signaling_send = signaling_send
        self.on_message = on_message

        self.pc: Optional[RTCPeerConnection] = None
        self.channel = None
        self.ready = asyncio.Event()
        self.closed = False
        self.connected = False

        config = RTCConfiguration(
            [RTCIceServer(**srv) for srv in (ice_servers or DEFAULT_STUN)]
        )
        self.pc = RTCPeerConnection(configuration=config)

        @self.pc.on("datachannel")
        def on_datachannel(channel):
            logger.info("WebRTC: datachannel opened from %s", self.remote_fp)
            self.channel = channel

            @channel.on("open")
            def on_open():
                logger.info("WebRTC: channel open → %s", self.remote_fp)
                self.connected = True
                self.ready.set()

            @channel.on("close")
            def on_close():
                logger.info("WebRTC: channel closed → %s", self.remote_fp)
                self.connected = False

            @channel.on("message")
            def on_message(msg):
                if isinstance(msg, str):
                    data = msg.encode("utf-8")
                else:
                    data = msg
                self.on_message(self.remote_fp, data)

        @self.pc.on("icecandidate")
        def on_icecandidate(candidate):
            if candidate is None:
                return
            cand = {
                "subtype": "webrtc-candidate",
                "candidate": candidate.to_sdp(),
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            self.signaling_send(self.remote_fp, cand)

    # ---------------------------------------------------------
    # OFFER / ANSWER
    # ---------------------------------------------------------

    async def create_offer(self):
        if self.closed:
            return

        if not self.channel:
            self.channel = self.pc.createDataChannel("data")

            @self.channel.on("open")
            def on_open():
                logger.info("WebRTC: channel open → %s", self.remote_fp)
                self.connected = True
                self.ready.set()

            @self.channel.on("close")
            def on_close():
                logger.info("WebRTC: channel closed → %s", self.remote_fp)
                self.connected = False

            @self.channel.on("message")
            def on_message(msg):
                if isinstance(msg, str):
                    data = msg.encode("utf-8")
                else:
                    data = msg
                self.on_message(self.remote_fp, data)

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        payload = {
            "subtype": "webrtc-offer",
            "sdp": self.pc.localDescription.sdp,
            "type": self.pc.localDescription.type,
        }
        self.signaling_send(self.remote_fp, payload)

    async def receive_offer(self, offer: Dict[str, Any]):
        if self.closed:
            return

        desc = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        await self.pc.setRemoteDescription(desc)

        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        payload = {
            "subtype": "webrtc-answer",
            "sdp": self.pc.localDescription.sdp,
            "type": self.pc.localDescription.type,
        }
        self.signaling_send(self.remote_fp, payload)

    async def receive_answer(self, answer: Dict[str, Any]):
        if self.closed:
            return

        desc = RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        await self.pc.setRemoteDescription(desc)
        self.ready.set()

    # ---------------------------------------------------------
    # ICE
    # ---------------------------------------------------------

    async def add_ice_candidate(self, cand: Dict[str, Any]):
        if self.closed:
            return
        try:
            candidate = RTCIceCandidate(
                sdpMid=cand.get("sdpMid"),
                sdpMLineIndex=cand.get("sdpMLineIndex"),
                candidate=cand.get("candidate"),
            )
            await self.pc.addIceCandidate(candidate)
        except Exception as e:
            logger.error("WebRTC: ICE error from %s: %s", self.remote_fp, e)

    # ---------------------------------------------------------
    # SEND
    # ---------------------------------------------------------

    async def send(self, data: bytes):
        if self.closed:
            return
        if not self.channel:
            await self.ready.wait()
        if self.channel:
            try:
                self.channel.send(data)
            except Exception as e:
                logger.error("WebRTC send error to %s: %s", self.remote_fp, e)

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    async def close(self):
        self.closed = True
        self.connected = False
        if self.pc:
            try:
                await self.pc.close()
            except Exception:
                pass
        self.pc = None
        self.channel = None


class WebRTCManager:
    """
    Управляет всеми WebRTCPeer.
    Даёт TransportLayer простой API:
      - connect_to(remote_fp)
      - send(remote_fp, data: bytes)
      - handle_signal(from_fp, signal: dict)
    """

    def __init__(
        self,
        local_fp: str,
        signaling_send: Callable[[str, Dict[str, Any]], None],
        on_message: Callable[[str, bytes], None],
        ice_servers: Optional[List[Dict[str, str]]] = None,
    ):
        self.local_fp = local_fp
        self.signaling_send = signaling_send
        self.on_message = on_message
        self.ice_servers = ice_servers or DEFAULT_STUN

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self._peers: Dict[str, WebRTCPeer] = {}
        self._lock = threading.Lock()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _get_or_create_peer(self, remote_fp: str) -> WebRTCPeer:
        if remote_fp == self.local_fp:
            raise ValueError("WebRTC cannot connect to itself")

        with self._lock:
            peer = self._peers.get(remote_fp)
            if peer is None:
                peer = WebRTCPeer(
                    local_fp=self.local_fp,
                    remote_fp=remote_fp,
                    loop=self._loop,
                    signaling_send=self.signaling_send,
                    on_message=self.on_message,
                    ice_servers=self.ice_servers,
                )
                self._peers[remote_fp] = peer
            return peer

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def connect_to(self, remote_fp: str):
        peer = self._get_or_create_peer(remote_fp)
        self._run_coro(peer.create_offer())

    def send(self, remote_fp: str, data: bytes) -> bool:
        with self._lock:
            peer = self._peers.get(remote_fp)
        if not peer:
            return False
        self._run_coro(peer.send(data))
        return True

    def handle_signal(self, from_fp: str, signal: Dict[str, Any]):
        subtype = signal.get("subtype")
        if not subtype:
            return

        peer = self._get_or_create_peer(from_fp)

        if subtype == "webrtc-offer":
            self._run_coro(peer.receive_offer(signal))
        elif subtype == "webrtc-answer":
            self._run_coro(peer.receive_answer(signal))
        elif subtype == "webrtc-candidate":
            self._run_coro(peer.add_ice_candidate(signal))

    def close_peer(self, remote_fp: str):
        with self._lock:
            peer = self._peers.pop(remote_fp, None)
        if peer:
            self._run_coro(peer.close())

    def shutdown(self):
        with self._lock:
            peers = list(self._peers.values())
            self._peers.clear()

        for p in peers:
            self._run_coro(p.close())

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)
