import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

@dataclass
class PlayerModel:
    player_id: str
    player_name: str
    hero_color: str
    hero_level: int
    hero_hp: int
    hero_shield: int
    position_x: float
    position_y: float
    is_host: bool
    anim_name: str = "idle"
    facing_right: bool = True
    hero_exp: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerModel":
        return cls(
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", "Jugador"),
            hero_color=data.get("hero_color", "Rojo"),
            hero_level=data.get("hero_level", 1),
            hero_hp=data.get("hero_hp", 50),
            hero_shield=data.get("hero_shield", 0),
            position_x=float(data.get("position_x", 0.0)),
            position_y=float(data.get("position_y", 0.0)),
            is_host=bool(data.get("is_host", False)),
            anim_name=data.get("anim_name", "idle"),
            facing_right=bool(data.get("facing_right", True)),
            hero_exp=int(data.get("hero_exp", 0))
        )

@dataclass
class RoomModel:
    room_code: str
    host_id: str
    players: Dict[str, PlayerModel] = field(default_factory=dict)
    max_players: int = 2
    created_at: float = field(default_factory=time.time)
    status: str = "LOBBY"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert player models to dicts
        d["players"] = {pid: p.to_dict() for pid, p in self.players.items()}
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoomModel":
        players_data = data.get("players", {})
        players = {pid: PlayerModel.from_dict(pinfo) for pid, pinfo in players_data.items()}
        return cls(
            room_code=data.get("room_code", ""),
            host_id=data.get("host_id", ""),
            players=players,
            max_players=data.get("max_players", 2),
            created_at=data.get("created_at", time.time()),
            status=data.get("status", "LOBBY")
        )
