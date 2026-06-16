import json
import os
import random
import string
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .room_manager import RoomManager
from .network_models import PlayerModel

app = FastAPI(title="Dungeon Dice Online Server")

room_manager = RoomManager()
active_connections: Dict[str, list] = {}

@app.get("/rooms/{room_code}")
async def check_room(room_code: str):
    room = room_manager.get_room(room_code)
    if room:
        print("[SERVIDOR] Sala encontrada", flush=True)
        if len(room.players) >= room.max_players:
            return {"exists": True, "full": True}
        return {"exists": True, "full": False}
    return {"exists": False}

@app.websocket("/ws/{room_code}/{player_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_id: str, player_name: str):
    await websocket.accept()
    print("[SERVIDOR] Jugador conectado", flush=True)
    room_code = room_code.upper()

    player = PlayerModel(
        player_id=player_id,
        player_name=player_name,
        hero_color="Rojo",
        hero_level=1,
        hero_hp=50,
        hero_shield=0,
        position_x=0.0,
        position_y=0.0,
        is_host=False
    )

    room = room_manager.get_room(room_code)
    if not room:
        room = room_manager.create_room(player, code=room_code, max_players=6)
        print("[SERVIDOR] Sala creada", flush=True)
    else:
        joined = room_manager.join_room(room_code, player)
        if not joined:
            await websocket.send_json({"type": "ERROR", "message": "Room full or unavailable"})
            await websocket.close()
            return

    if room_code not in active_connections:
        active_connections[room_code] = []
    active_connections[room_code].append(websocket)

    join_msg = {
        "type": "PLAYER_JOINED",
        "player": player.to_dict(),
        "room": room_manager.get_room(room_code).to_dict()
    }
    await broadcast_to_room(room_code, join_msg)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "SYNC_PLAYER":
                pdata = data.get("player")
                if pdata:
                    pid = pdata.get("player_id")
                    room = room_manager.get_room(room_code)
                    if room and pid in room.players:
                        player_model = room.players[pid]
                        player_model.hero_color = pdata.get("hero_color", player_model.hero_color)
                        player_model.hero_level = pdata.get("hero_level", player_model.hero_level)
                        player_model.hero_hp = pdata.get("hero_hp", player_model.hero_hp)
                        player_model.hero_shield = pdata.get("hero_shield", player_model.hero_shield)
                        player_model.position_x = pdata.get("position_x", player_model.position_x)
                        player_model.position_y = pdata.get("position_y", player_model.position_y)
                        player_model.is_host = pdata.get("is_host", player_model.is_host)
                        player_model.anim_name = pdata.get("anim_name", player_model.anim_name)
                        player_model.facing_right = pdata.get("facing_right", player_model.facing_right)
                        player_model.hero_exp = pdata.get("hero_exp", player_model.hero_exp)
                        
                        update_msg = {
                            "type": "ROOM_UPDATE",
                            "room": room.to_dict()
                        }
                        await broadcast_to_room(room_code, update_msg)
                        continue
            elif msg_type == "START_GAME":
                room = room_manager.get_room(room_code)
                if room:
                    room.status = "PLAYING"
                await broadcast_to_room(room_code, data)
                continue

            await broadcast_to_room(room_code, data, exclude=websocket)
    except WebSocketDisconnect:
        if room_code in active_connections:
            active_connections[room_code].remove(websocket)
            if not active_connections[room_code]:
                del active_connections[room_code]

        updated_room = room_manager.leave_room(room_code, player_id)
        print("[SERVIDOR] Jugador desconectado", flush=True)
        if updated_room:
            leave_msg = {
                "type": "PLAYER_LEFT",
                "player_id": player_id,
                "player_name": player_name,
                "room": updated_room.to_dict()
            }
            await broadcast_to_room(room_code, leave_msg)
        else:
            room_manager.close_room(room_code)
            print("[SERVIDOR] Sala eliminada", flush=True)

async def broadcast_to_room(room_code: str, message: dict, exclude: WebSocket = None):
    connections = active_connections.get(room_code, [])
    for conn in connections:
        if conn != exclude:
            try:
                await conn.send_json(message)
            except Exception:
                pass