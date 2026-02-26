# relay_server.py
# Центральный relay-сервер FIEP.
# Принимает клиентов, пересылает envelopes, обновляет DAG, UDP, WebRTC.

import asyncio
import json
import time
from typing import Dict, Any

from dag_manager import DAGManager
from udp_registry import UDPRegistry
from webrtc_signaling import WebRTCSignaling
from centrallogging import CentralLogger
from config import PORT

logger = CentralLogger("relay_server")

# fingerprint → writer
clients: Dict[str, asyncio.StreamWriter] = {}

dag = DAGManager()
udp = UDPRegistry(dag)
webrtc = WebRTCSignaling(dag)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    fp = None
    addr = writer.get_extra_info("peername")
    logger.info(f"Incoming connection from {addr}")

    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break

            try:
                env = json.loads(raw.decode("utf-8"))
            except Exception:
                logger.error("Invalid JSON from client")
                continue

            etype = env.get("type")

            # -------------------------------
            # REGISTER
            # -------------------------------
            if etype == "register":
                fp = env.get("fingerprint")
                if not fp:
                    logger.error("Client tried to register without fingerprint")
                    break

                clients[fp] = writer

                dag.update_node(fp, {
                    "address": env.get("public_ip"),
                    "port": env.get("port"),
                    "local_ip": env.get("local_ip"),
                    "supports_webrtc": env.get("supports_webrtc", False),
                    "last_seen": int(time.time())
                })

                logger.info(f"Registered client {fp} from {addr}")

                # Рассылаем DAG всем
                await broadcast_dag()
                continue

            # -------------------------------
            # PING
            # -------------------------------
            if etype == "ping":
                if fp:
                    dag.touch(fp)
                continue

            # -------------------------------
            # UDP-INFO
            # -------------------------------
            if etype == "udp-info":
                if fp:
                    udp.update(fp, env)
                    await broadcast_dag()
                continue

            # -------------------------------
            # WebRTC signaling
            # -------------------------------
            if etype == "webrtc":
                await webrtc.forward(env, clients)
                continue

            # -------------------------------
            # DAG update from client (optional)
            # -------------------------------
            if etype == "dag-update":
                dag.merge(env.get("node"))
                await broadcast_dag()
                continue

            # -------------------------------
            # MESSAGE
            # -------------------------------
            if etype == "message":
                to = env.get("to")
                if to in clients:
                    try:
                        clients[to].write((json.dumps(env) + "\n").encode())
                        await clients[to].drain()
                        logger.debug(f"Forwarded message {fp} → {to}")
                    except Exception:
                        logger.error(f"Failed to forward message to {to}")
                continue

    except Exception as e:
        logger.error(f"Client error: {e}")

    finally:
        if fp and fp in clients:
            del clients[fp]
            dag.remove(fp)
            await broadcast_dag()

        writer.close()
        await writer.wait_closed()
        logger.info(f"Client disconnected: {fp}")


async def broadcast_dag():
    env = {
        "type": "dag",
        "nodes": dag.get_all()
    }
    data = (json.dumps(env) + "\n").encode()

    for fp, w in list(clients.items()):
        try:
            w.write(data)
            await w.drain()
        except Exception:
            logger.error(f"Failed to send DAG to {fp}")


async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", PORT)
    logger.info(f"Central relay running on port {PORT}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
