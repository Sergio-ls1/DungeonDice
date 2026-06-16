import random
import string
import time
from typing import Dict, Optional
from .network_models import RoomModel, PlayerModel

class RoomManager:
    def __init__(self):
        # Maps room_code -> RoomModel
        self.rooms: Dict[str, RoomModel] = {}

    def generate_code(self, length: int = 6) -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choice(chars) for _ in range(length))
            if code not in self.rooms:
                return code

    def create_room(self, host_player: PlayerModel, code: Optional[str] = None, max_players: int = 2) -> RoomModel:
        if code is None:
            code = self.generate_code()
        else:
            code = code.upper()
        host_player.is_host = True
        room = RoomModel(
            room_code=code,
            host_id=host_player.player_id,
            players={host_player.player_id: host_player},
            max_players=max_players,
            created_at=time.time()
        )
        self.rooms[code] = room
        return room

    def join_room(self, code: str, player: PlayerModel) -> Optional[RoomModel]:
        code = code.upper()
        if code not in self.rooms:
            return None
        room = self.rooms[code]
        if len(room.players) >= room.max_players:
            return None # Room is full
        player.is_host = False
        room.players[player.player_id] = player
        return room

    def leave_room(self, code: str, player_id: str) -> Optional[RoomModel]:
        code = code.upper()
        if code not in self.rooms:
            return None
        room = self.rooms[code]
        if player_id in room.players:
            del room.players[player_id]
        
        # If room is empty or host left, we might close the room or transfer host
        if not room.players:
            self.close_room(code)
            return None
        
        if player_id == room.host_id:
            # Transfer host to the next player
            next_host_id = list(room.players.keys())[0]
            room.host_id = next_host_id
            room.players[next_host_id].is_host = True
            
        return room

    def close_room(self, code: str) -> bool:
        code = code.upper()
        if code in self.rooms:
            del self.rooms[code]
            return True
        return False

    def get_room(self, code: str) -> Optional[RoomModel]:
        return self.rooms.get(code.upper())
