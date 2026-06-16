import json
import os
import random
import string
import time
import queue
import threading
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path


def resource_path(relative_path):
    import sys
    
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
        
    p = Path(relative_path)
    if p.is_absolute():
        try:
            file_path = Path(__file__).resolve()
            if "engine" in file_path.parts:
                root_path = file_path.parents[2]
            elif "network" in file_path.parts:
                root_path = file_path.parents[2]
            else:
                root_path = file_path.parents[1]
            p = p.relative_to(root_path)
        except Exception:
            pass
    return os.path.join(base_path, str(p))


# Load URL from config file
def get_server_url() -> str:
    config_path = os.path.join("config", "network.json")
    url = "wss://dungeondice-server.onrender.com"
    
    target_path = config_path
    if not os.path.exists(target_path):
        target_path = resource_path(config_path)
        
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                url = config.get("server_url", url)
        except Exception as e:
            print(f"Error reading network config: {e}")
            
    url = url.rstrip('/')
    if url.startswith("https://"):
        url = "wss://" + url[8:]
    elif url.startswith("http://"):
        url = "ws://" + url[7:]
    return url

# Server application (FastAPI & WebSockets) - imported from server_app.py
try:
    from .server_app import app
    HAS_SERVER = True
except ImportError:
    app = None
    HAS_SERVER = False

# Client implementation (GameClient)
try:
    import websockets
    HAS_CLIENT = True
except ImportError:
    HAS_CLIENT = False

class GameClient:
    def __init__(self):
        self.server_url = get_server_url()
        self.websocket = None
        self.thread = None
        self.loop = None
        self.send_queue = queue.Queue()
        self.receive_queue = queue.Queue()
        self.state = "DISCONNECTED"  # DISCONNECTED, CONNECTING, CONNECTED, FAILED
        self.room_code = ""
        self.player_id = ""
        self.player_name = ""

    def connect(self, room_code: str, player_id: str, player_name: str):
        if not HAS_CLIENT:
            print("[GameClient] websockets library not installed. Running in mock/offline mode.")
            self.state = "CONNECTED"
            self.room_code = room_code.upper()
            self.player_id = player_id
            self.player_name = player_name
            # Queue a mock join message
            self.receive_queue.put({
                "type": "PLAYER_JOINED",
                "player": {
                    "player_id": player_id,
                    "player_name": player_name,
                    "hero_color": "Rojo",
                    "hero_level": 1,
                    "hero_hp": 50,
                    "hero_shield": 0,
                    "position_x": 0.0,
                    "position_y": 0.0,
                    "is_host": True
                },
                "room": {
                    "room_code": room_code.upper(),
                    "host_id": player_id,
                    "players": {
                        player_id: {
                            "player_id": player_id,
                            "player_name": player_name,
                            "hero_color": "Rojo",
                            "hero_level": 1,
                            "hero_hp": 50,
                            "hero_shield": 0,
                            "position_x": 0.0,
                            "position_y": 0.0,
                            "is_host": True
                        }
                    },
                    "max_players": 2,
                    "created_at": time.time()
                }
            })
            return

        self.room_code = room_code.upper()
        self.player_id = player_id
        self.player_name = player_name
        self.state = "CONNECTING"

        # Start async connection handler in daemon thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connection_handler())
        except BaseException:
            pass
        finally:
            try:
                self.loop.close()
            except Exception:
                pass

    async def _connection_handler(self):
        uri = f"{self.server_url}/ws/{self.room_code}/{self.player_id}/{self.player_name}"
        print("[CLIENTE] Intentando conectar", flush=True)
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                self.state = "CONNECTED"
                print(f"[GameClient] Connected to server at {uri}")
                print("[CLIENTE] Conectado", flush=True)

                await asyncio.gather(
                    self._send_loop(),
                    self._receive_loop()
                )
        except Exception as e:
            if self.state != "DISCONNECTED":
                print(f"[GameClient] Connection error: {e}")
            print("[CLIENTE] Error de conexión", flush=True)
            self.state = "FAILED"
        finally:
            self.state = "DISCONNECTED"
            self.websocket = None

    async def _send_loop(self):
        while self.state == "CONNECTED" and self.websocket is not None:
            try:
                msg = await self.loop.run_in_executor(None, self.send_queue.get_nowait)
                await self.websocket.send(json.dumps(msg))
            except queue.Empty:
                await asyncio.sleep(0.05)
            except Exception as e:
                if self.state != "DISCONNECTED":
                    print(f"[GameClient] Send error: {e}")
                break

    async def _receive_loop(self):
        while self.state == "CONNECTED" and self.websocket is not None:
            try:
                msg_str = await self.websocket.recv()
                msg = json.loads(msg_str)
                self.receive_queue.put(msg)
            except Exception as e:
                if self.state != "DISCONNECTED":
                    print(f"[GameClient] Receive error: {e}")
                break

    def send_message(self, message: dict):
        if not HAS_CLIENT:
            print(f"[GameClient Mock Send] {message}")
            return
        self.send_queue.put(message)

    def get_message(self) -> Optional[dict]:
        try:
            return self.receive_queue.get_nowait()
        except queue.Empty:
            return None

    def disconnect(self):
        self.state = "DISCONNECTED"
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
