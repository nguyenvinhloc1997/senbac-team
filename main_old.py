from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed
from urllib.parse import urlparse, parse_qs
import base64
import json
import asyncio
from pathlib import Path
from typing import Dict, Set
import logging
import uvicorn

app = FastAPI()

# Configuration
PCM_FILE = "audio/16bit-8000.pcm"
REPEAT_FILE = "audio/repeat.wav"
TEST_FILE = "audio/woman_4.wav"
SAMPLE_RATE = 44100
BYTE_PER_SAMPLE = 2
CHANNELS = 2
BYTES_CHUNK = SAMPLE_RATE * BYTE_PER_SAMPLE * CHANNELS

# Global state
clients: Set[WebSocket] = set()
servers: Set[WebSocket] = set()
pcm_data: bytes = None
offset: int = 0
send_task: asyncio.Task = None

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def try_parse_json(json_string: str) -> dict:
    """Attempt to parse a JSON string, return dict or None."""
    try:
        obj = json.loads(json_string)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None

def base64_to_bytes(base64_str: str) -> bytes:
    """Convert base64 string to bytes."""
    return base64.b64decode(base64_str)

async def send_payload_to_clients(payload: bytes | str):
    """Send payload to all connected clients."""
    for client in clients.copy():
        try:
            if isinstance(payload, bytes):
                await client.send_bytes(payload)
            else:
                await client.send_text(payload)
        except (WebSocketDisconnect, ConnectionClosed):
            clients.discard(client)
            logger.info("Client disconnected during send")

async def send_payload_to_servers(payload: str):
    """Send payload to all connected servers."""
    for server in servers.copy():
        try:
            await server.send_text(payload)
        except (WebSocketDisconnect, ConnectionClosed):
            servers.discard(server)
            logger.info("Server disconnected during send")

async def send_data():
    """Send chunks of PCM data to clients."""
    global offset, pcm_data, send_task
    if not pcm_data:
        return
    while offset < len(pcm_data):
        payload = pcm_data[offset:offset + BYTES_CHUNK]
        offset += BYTES_CHUNK
        await send_payload_to_clients(payload)
        await asyncio.sleep(1)  # Simulate streaming interval
    offset = 0  # Reset offset when done
    send_task = None

@app.websocket("/server/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Socket connected. Processing...")

    # Parse client type from query parameters
    query_params = parse_qs(urlparse(websocket.scope["query_string"].decode()).query)
    client_type = query_params.get("clientType", ["player"])[0]
    logger.info(f"Client type: {client_type}")

    # Register client or server
    if client_type == "player":
        clients.add(websocket)
    elif client_type == "server":
        servers.add(websocket)

    try:
        while True:
            data = await websocket.receive()
            is_binary = "bytes" in data
            message = data["bytes"] if is_binary else data["text"]

            if not is_binary:
                if message == "test":
                    payload = json.dumps({
                        "call_id": "test",
                        "channel": "stereo"
                    })
                    await send_payload_to_clients(payload)
                    try:
                        pcm_data_global = Path(PCM_FILE).read_bytes()
                        global pcm_data, offset, send_task
                        pcm_data = pcm_data_global
                        offset = 0
                        if send_task is None or send_task.done():
                            send_task = asyncio.create_task(send_data())
                    except Exception as e:
                        logger.error(f"Error reading PCM file: {e}")
                        raise
                    continue

                elif message == "stream_repeat":
                    try:
                        data = Path(REPEAT_FILE).read_bytes()
                        payload = json.dumps({
                            "event": "media",
                            "media": {
                                "payload": base64.b64encode(data).decode()
                            }
                        })
                        await send_payload_to_servers(payload)
                    except Exception as e:
                        logger.error(f"Error reading repeat file: {e}")
                        raise
                    continue

                elif message == "stream_repeat_sync":
                    try:
                        data = Path(REPEAT_FILE).read_bytes()
                        payload = json.dumps({
                            "event": "media",
                            "media": {
                                "payload": base64.b64encode(data).decode(),
                                "is_sync": True
                            }
                        })
                        await send_payload_to_servers(payload)
                    except Exception as e:
                        logger.error(f"Error reading repeat file: {e}")
                        raise
                    continue

                elif message == "hangup":
                    payload = json.dumps({"event": "hangup"})
                    await send_payload_to_servers(payload)
                    continue

                else:
                    msg = try_parse_json(message)
                    if msg:
                        if msg.get("event") == "media" and msg.get("media", {}).get("payload"):
                            await send_payload_to_clients(base64_to_bytes(msg["media"]["payload"]))
                            continue
                        elif msg.get("event") == "connected":
                            logger.info("Starting new call")
                            try:
                                data = Path(TEST_FILE).read_bytes()
                                payload = json.dumps({
                                    "event": "media",
                                    "media": {
                                        "payload": base64.b64encode(data).decode(),
                                        "is_sync": True
                                    }
                                })
                                await send_payload_to_clients(payload)
                            except Exception as e:
                                logger.error(f"Error reading test file: {e}")
                                raise
                            continue

            # Default: send binary message to clients
            # await send_payload_to_clients(message)

    except (WebSocketDisconnect, ConnectionClosed):
        logger.info("Disconnected")
        if client_type == "server":
            payload = json.dumps({"event": "close"})
            await send_payload_to_clients(payload)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        clients.discard(websocket)
        servers.discard(websocket)

if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8888)