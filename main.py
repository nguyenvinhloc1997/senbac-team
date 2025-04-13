import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from websockets.exceptions import ConnectionClosed
from urllib.parse import urlparse, parse_qs
import base64
import json
import asyncio
from pathlib import Path
from typing import Dict, Set
import logging
from pydub import AudioSegment
import io
import uvicorn
import os

app = FastAPI()

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent
WAV_STEREO = os.path.join(PROJECT_ROOT, "audio", "3_stereo.wav")
WAV_MONO = os.path.join(PROJECT_ROOT, "audio", "10_mono.wav")

# Audio configuration
SAMPLE_RATE = 8000
BYTE_PER_SAMPLE = 2
CHANNELS = 1
FRAME_SAMPLES = 1152  # One MP3 frame contains 1152 samples
FRAME_MS = int((FRAME_SAMPLES / SAMPLE_RATE) * 1000)  # ~144ms per frame

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

async def send_payload_to_clients(payload: bytes | str | dict, data_type="text"):
    """Send payload to all connected clients."""
    for client in clients.copy():
        try:
            if data_type == "binary":
                await client.send_bytes(payload)
            if data_type == "json":
                await client.send_json(payload)
            if data_type == "text":
                await client.send_text(payload)
        except (WebSocketDisconnect, ConnectionClosed):
            clients.discard(client)
            logger.error("Client disconnected during send")

async def send_chunks():
    """
    Process and send audio chunks to clients, one MP3 frame per chunk.
    """
    try:
        # Read and convert the WAV file
        audio_segment = AudioSegment.from_wav(WAV_MONO)
        
        # Log total audio information
        total_duration = len(audio_segment) / 1000.0  # Convert milliseconds to seconds
        logger.info(f"Total audio file:")
        logger.info(f"  - Duration: {total_duration:.3f} seconds")
        
        # Convert entire file to MP3 once
        buffer = io.BytesIO()
        audio_segment.export(
            buffer,
            format='mp3',
            bitrate='8k',
            parameters=[
                "-ac", str(CHANNELS),
                "-ar", str(SAMPLE_RATE)
            ]
        )
        mp3_data = buffer.getvalue()
        
        logger.info(f"Total MP3 data size: {len(mp3_data)} bytes")
        
        # Find the start of actual audio data (after metadata)
        # MP3 sync word is 0xFF 0xFB
        audio_start = 0
        for i in range(len(mp3_data) - 1):
            if mp3_data[i] == 0xFF and mp3_data[i+1] == 0xFB:
                audio_start = i
                break
                
        logger.info(f"Found audio data starting at byte {audio_start}")
        
        # Calculate frame size based on average MP3 frame size
        # For 8k bitrate, each frame is roughly 400-600 bytes
        frame_size = 549  # Based on observed frame size from logs
        
        # Calculate number of frames
        total_frames = (len(mp3_data) - audio_start) // frame_size
        logger.info(f"Will create {total_frames} chunks (one frame per chunk)")
        logger.info(f"Remaining bytes: {len(mp3_data) - audio_start}")
        
        frame_count = 0
        
        # Process one frame at a time
        for i in range(audio_start, len(mp3_data), frame_size):
            # Extract one frame of MP3 data
            frame_data = mp3_data[i:i + frame_size]
            
            # Skip empty frames
            if len(frame_data) == 0:
                continue
                
            # Create message
            message = {
                "event": "chunk",
                "media": {
                    "payload": base64.b64encode(frame_data).decode('utf-8'),
                    "is_sync": True
                }
            }
            
            # Log frame details
            logger.info(f"Frame {frame_count + 1}/{total_frames}:")
            logger.info(f"  - Start byte: {i}")
            logger.info(f"  - Frame size: {len(frame_data)} bytes")
            logger.info(f"  - First few bytes: {frame_data[:10].hex()}")
            
            await send_payload_to_clients(message, 'json')
            
            # Sleep for half a frame duration
            await asyncio.sleep(FRAME_MS / 2000.0)
            
            frame_count += 1
            
        # Send any remaining data as the last frame
        remaining_data = mp3_data[audio_start + (frame_count * frame_size):]
        if len(remaining_data) > 0:
            message = {
                "event": "chunk",
                "media": {
                    "payload": base64.b64encode(remaining_data).decode('utf-8'),
                    "is_sync": True
                }
            }
            
            logger.info(f"Final frame:")
            logger.info(f"  - Start byte: {audio_start + (frame_count * frame_size)}")
            logger.info(f"  - Frame size: {len(remaining_data)} bytes")
            logger.info(f"  - First few bytes: {remaining_data[:10].hex()}")
            
            await send_payload_to_clients(message, 'json')
            frame_count += 1
            
        logger.info(f"Sent {frame_count} frames")

    except Exception as e:
        logger.error(f"Error in send_chunks: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Socket connected.")

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
            if is_binary:
                continue

            raw_message = data["bytes"] if is_binary else data["text"]
            
            msg = try_parse_json(raw_message)
            if msg:
                if msg.get("event") == "media" and msg.get("media", {}).get("payload"):
                    continue
                elif msg.get("event") == "connected":
                    logger.info("Starting new call")
                    await send_chunks()
                    continue

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