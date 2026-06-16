import pygame
import sys
import os
import math
import random
import string
import threading
from pathlib import Path
from engine.battle import BattleSystem
from engine.entities import Hero
from engine.save import load_game, save_game, SAVE_PATH
from engine.map import MapSystem
from network.server_client import GameClient

# Create required directories
for d in ["assets/fonts", "assets/sprites", "data", "engine"]:
    os.makedirs(d, exist_ok=True)

pygame.init()

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 640
FPS = 60

screen = pygame.display.set_mode((1024, 640), pygame.RESIZABLE)
pygame.display.set_caption("Dungeon Dice")
clock = pygame.time.Clock()

# Override mouse coordinates scaling for resizable display
_orig_get_pos = pygame.mouse.get_pos

def get_scaled_mouse_pos():
    mx, my = _orig_get_pos()
    sw, sh = pygame.display.get_surface().get_size()
    if sw > 0 and sh > 0:
        return (int(mx * 1024 / sw), int(my * 640 / sh))
    return (mx, my)

pygame.mouse.get_pos = get_scaled_mouse_pos

# Override pygame.event.get to scale mouse event positions to 1024x640
_orig_event_get = pygame.event.get

def get_scaled_events(*args, **kwargs):
    events = _orig_event_get(*args, **kwargs)
    surf = pygame.display.get_surface()
    if not surf:
        return events
    sw, sh = surf.get_size()
    if sw <= 0 or sh <= 0:
        return events
        
    scaled_events = []
    for ev in events:
        if hasattr(ev, "pos"):
            lx = int(ev.pos[0] * 1024 / sw)
            ly = int(ev.pos[1] * 640 / sh)
            attrs = dict(ev.__dict__)
            attrs["pos"] = (lx, ly)
            if "rel" in attrs:
                rx = int(attrs["rel"][0] * 1024 / sw)
                ry = int(attrs["rel"][1] * 640 / sh)
                attrs["rel"] = (rx, ry)
            scaled_events.append(pygame.event.Event(ev.type, attrs))
        else:
            scaled_events.append(ev)
    return scaled_events

pygame.event.get = get_scaled_events


def resource_path(relative_path):
    import os
    import sys
    from pathlib import Path
    
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
        
    if hasattr(relative_path, "relative_to"):
        try:
            file_path = Path(__file__).resolve()
            if "engine" in file_path.parts:
                root_path = file_path.parents[2]
            elif "network" in file_path.parts:
                root_path = file_path.parents[2]
            else:
                root_path = file_path.parents[1]
            relative_path = Path(relative_path).relative_to(root_path)
        except Exception:
            pass
    return os.path.join(base_path, str(relative_path))


def get_font(size):
    font_path = "assets/fonts/pixel.ttf"
    res_font = resource_path(font_path)
    if os.path.exists(res_font):
        return pygame.font.Font(res_font, size)
    return pygame.font.SysFont("courier", size, bold=True)


BASE = Path(__file__).resolve().parents[1]
FOREST = (
    BASE
    / "tiny-RPG-forest-files"
    / "tiny-RPG-forest-files"
    / "Assets"
    / "PNG"
)


def _load_sheet(path, frame_w, frame_h, num_frames, scale=1):
    """Return list of pygame.Surface frames from a horizontal spritesheet."""
    frames = []
    res_path = resource_path(path)
    if not os.path.exists(res_path):
        return frames
    sheet = pygame.image.load(res_path).convert_alpha()
    for i in range(num_frames):
        rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
        frame = sheet.subsurface(rect).copy()
        if scale != 1:
            w, h = frame.get_size()
            frame = pygame.transform.scale(frame, (w * scale, h * scale))
        frames.append(frame)
    return frames


class Game:
    def __init__(self):
        self.hero = Hero()
        self.map_system = MapSystem(self.hero)
        self.battle = None
        self.state = "MENU"
        self.is_multiplayer = False
        self.game_client = None
        self.player_id = ""
        self.is_host = False
        self.room_code = ""
        self.has_synced_initial_player = False
        self.room_data = None
        self.lobby_notifications = []
        self.room_check_error = ""
        self.checking_room_thread = None
        self.checking_room_result = None

        self.font_small = get_font(16)
        self.font_medium = get_font(24)
        self.font_large = get_font(32)
        self.font_title = get_font(64)
        self.font_subtitle = get_font(20)

        self.reset_last_sent_state()

        # ---- menu visuals ----
        self._load_menu_assets()

    def reset_last_sent_state(self):
        self.last_sent_pos_x = None
        self.last_sent_pos_y = None
        self.last_sent_anim = None
        self.last_sent_facing = None
        self.last_sent_color = None
        self.last_sent_lvl = None
        self.last_sent_hp = None
        self.last_sent_shield = None
        self.last_sent_exp = None
        self.progress_sync_timer = 0.0
        self.menu_scroll = 0.0
        self.menu_anim_timer = 0.0
        self.menu_selection = 0
        self.menu_options_list = [
            "NUEVA PARTIDA",
            "CARGAR PARTIDA",
            "CREAR PARTIDA",
            "UNIRSE A PARTIDA",
            "SALIR"
        ]
        self.colors_available = [
            {"name": "Verde",    "rgb": (60, 200, 100)},
            {"name": "Azul",     "rgb": (60, 120, 220)},
            {"name": "Rojo",     "rgb": (220, 60, 60)},
            {"name": "Morado",   "rgb": (150, 80, 220)},
            {"name": "Amarillo", "rgb": (240, 220, 50)},
            {"name": "Naranja",  "rgb": (240, 130, 40)}
        ]
        self.selected_color_idx = 0
        self.saved_games = []
        self.load_page = 0
        self.confirm_delete_save = None
        self.codigo_input = ""
        self.menu_state = "MAIN"
        self.name_input_target_state = ""
        self.player_name_input = ""

    def _load_menu_assets(self):
        """Pre-load tile and sprite assets for the menu."""
        tileset_path = FOREST / "environment" / "tileset.png"
        self.menu_tile_grass = None
        self.menu_tile_path = None
        self.menu_tile_dark = None
        res_tileset = resource_path(tileset_path)
        if os.path.exists(res_tileset):
            tileset = pygame.image.load(res_tileset).convert_alpha()
            self.menu_tile_grass = pygame.transform.scale(
                tileset.subsurface(pygame.Rect(0, 0, 16, 16)), (32, 32)
            )
            self.menu_tile_path = pygame.transform.scale(
                tileset.subsurface(pygame.Rect(16, 0, 16, 16)), (32, 32)
            )
            self.menu_tile_dark = pygame.transform.scale(
                tileset.subsurface(pygame.Rect(0, 96, 16, 16)), (32, 32)
            )

        sliced = FOREST / "environment" / "sliced-objects"
        self.menu_trees = []
        for name in ["tree-orange.png", "tree-pink.png"]:
            tp = sliced / name
            res_tp = resource_path(tp)
            if os.path.exists(res_tp):
                img = pygame.image.load(res_tp).convert_alpha()
                w, h = img.get_size()
                img = pygame.transform.scale(img, (w * 2, h * 2))
                self.menu_trees.append(img)

        self._build_menu_bg()

        hero_walk_path = FOREST / "spritesheets" / "hero" / "walk" / "hero-walk-front.png"
        self.menu_hero_frames = _load_sheet(hero_walk_path, 32, 32, 6, scale=4)
        if not self.menu_hero_frames:
            hero_idle_path = FOREST / "spritesheets" / "hero" / "idle" / "hero-idle-front.png"
            self.menu_hero_frames = _load_sheet(hero_idle_path, 32, 32, 1, scale=4)

        treant_path = FOREST / "spritesheets" / "treant" / "walk" / "treant-walk-front.png"
        self.menu_treant_frames = _load_sheet(treant_path, 31, 35, 4, scale=4)
        if not self.menu_treant_frames:
            treant_idle = FOREST / "spritesheets" / "treant" / "idle" / "treant-idle-front.png"
            self.menu_treant_frames = _load_sheet(treant_idle, 31, 35, 1, scale=4)

        self.menu_particles = []
        for _ in range(40):
            self.menu_particles.append({
                "x": random.uniform(0, 1024),
                "y": random.uniform(0, 640),
                "speed": random.uniform(8, 25),
                "size": random.randint(1, 3),
                "alpha": random.randint(60, 180),
                "drift": random.uniform(-0.3, 0.3),
            })

    def _build_menu_bg(self):
        """Build a wide background strip from tiles for scrolling."""
        strip_w = 1024 + 64
        strip_h = 640
        self.menu_bg_strip = pygame.Surface((strip_w, strip_h))
        self.menu_bg_strip.fill((10, 5, 20))
        if not self.menu_tile_grass:
            return
        rng = random.Random(42)
        tw = 32
        for y in range(0, strip_h, tw):
            for x in range(0, strip_w, tw):
                row = y // tw
                if 8 <= row <= 11:
                    tile = self.menu_tile_path
                else:
                    if rng.random() < 0.08 and self.menu_tile_dark:
                        tile = self.menu_tile_dark
                    else:
                        tile = self.menu_tile_grass
                self.menu_bg_strip.blit(tile, (x, y))
        if self.menu_trees:
            for _ in range(18):
                tree = rng.choice(self.menu_trees)
                tx = rng.randint(0, strip_w - 64)
                row_band = rng.choice(["top", "bottom"])
                if row_band == "top":
                    ty = rng.randint(0, 180)
                else:
                    ty = rng.randint(420, strip_h - 80)
                self.menu_bg_strip.blit(tree, (tx, ty))

    def auto_save(self):
        if not hasattr(self.hero, 'current_save_path') or not self.hero.current_save_path:
            return
        import datetime
        self.hero.last_saved_date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_data = self.hero.get_data()
        if hasattr(self, 'map_system') and self.map_system:
            save_data["pos_x"] = self.map_system.pos_x
            save_data["pos_y"] = self.map_system.pos_y
            save_data["camera_x"] = self.map_system.camera_x
            save_data["camera_y"] = self.map_system.camera_y
            save_data["map_steps"] = self.map_system.steps
        from engine.save import save_game
        save_game(save_data, self.hero.current_save_path)

    def start_battle(self, enemy):
        self.battle = BattleSystem(self.hero, enemy, is_multiplayer=self.is_multiplayer)
        self.state = "BATTLE"

    # ------------------------------------------------------------------
    # MENU state
    # ------------------------------------------------------------------
    def _update_menu(self, dt):
        self.menu_scroll = (self.menu_scroll + dt * 15) % (1024 + 64)
        self.menu_anim_timer += dt
        
        # Check background room verification
        if hasattr(self, 'menu_state') and self.menu_state == "CHECKING_ROOM":
            if self.checking_room_result is not None:
                res = self.checking_room_result
                self.checking_room_result = None
                if res.get("exists") and not res.get("full"):
                    self.menu_state = "ROOM_FOUND"
                    self.room_check_error = ""
                else:
                    if res.get("full"):
                        self.room_check_error = "La sala esta llena."
                    elif "error" in res:
                        self.room_check_error = "Error de conexion."
                        print("[CLIENTE] Error de conexión", flush=True)
                    else:
                        self.room_check_error = "Sala no encontrada."
                        print("[CLIENTE] Error de conexión", flush=True)
                    self.menu_state = "JOIN_LOBBY"

        # Poll websocket messages if client exists
        if self.game_client:
            # Check connection state
            if self.game_client.state == "CONNECTED" and not self.has_synced_initial_player:
                # Send SYNC_PLAYER on initial connection
                sync_msg = {
                    "type": "SYNC_PLAYER",
                    "player": {
                        "player_id": self.player_id,
                        "player_name": self.hero.name,
                        "hero_color": self.hero.hero_color_name,
                        "hero_level": self.hero.level,
                        "hero_hp": self.hero.hp,
                        "hero_shield": self.hero.shield,
                        "position_x": 0.0,
                        "position_y": 0.0,
                        "is_host": self.is_host,
                        "hero_exp": self.hero.hero_exp
                    }
                }
                self.game_client.send_message(sync_msg)
                self.has_synced_initial_player = True
                self.menu_state = "LOBBY"
                if self.is_host:
                    print(f"[NET_LOG] HOST: Sala creada con codigo {self.room_code}")
                    self.lobby_notifications = [] # Reset on creation

            # Check if connection failed
            if self.game_client.state == "FAILED":
                print("[Game] Connection failed.")
                print("[CLIENTE] Error de conexión", flush=True)
                self.game_client.disconnect()
                self.game_client = None
                self.menu_state = "MAIN"
                self.is_multiplayer = False

            # Check messages in queue
            while True:
                msg = self.game_client.get_message()
                if not msg:
                    break
                
                mtype = msg.get("type")
                if mtype in ("PLAYER_JOINED", "PLAYER_LEFT", "ROOM_UPDATE"):
                    if mtype == "PLAYER_JOINED":
                        # Log/Notify visual when someone joins
                        p_info = msg.get("player")
                        if p_info:
                            p_id = p_info.get("player_id")
                            p_name = p_info.get("player_name", "Jugador")
                            if p_id != self.player_id:
                                # Host log
                                if self.is_host:
                                    print(f"[NET_LOG] HOST: Jugador conectado: {p_name}")
                                # Append visual notification
                                import time as ttime
                                self.lobby_notifications.append((f"{p_name} se ha unido.", ttime.time()))

                    elif mtype == "PLAYER_LEFT":
                        # Log/Notify visual when someone leaves
                        p_id = msg.get("player_id")
                        p_name = msg.get("player_name", "Alguien")
                        if p_name == "Alguien" and self.room_data and "players" in self.room_data:
                            orig_p = self.room_data["players"].get(p_id)
                            if orig_p:
                                p_name = orig_p.get("player_name", "Jugador")
                        # Host log
                        if self.is_host:
                            print(f"[NET_LOG] HOST: Jugador desconectado: {p_name}")
                        # Append visual notification
                        import time as ttime
                        self.lobby_notifications.append((f"{p_name} abandonó la sala.", ttime.time()))

                    self.room_data = msg.get("room")
                    if self.room_data:
                        self.room_code = self.room_data.get("room_code", self.room_code)
                        self._resolve_color_conflict()
                        # Client confirmation log
                        if not self.is_host and self.menu_state == "CONNECTING":
                            print(f"[NET_LOG] CLIENTE: Unión a sala {self.room_code} confirmada.")
                            self.lobby_notifications = [] # Reset on join

                elif mtype == "START_GAME":
                    self.state = "MAP"
                    self.menu_state = "MAIN"
                elif mtype == "ERROR":
                    print(f"[Game] Server error: {msg.get('message')}")
                    print("[CLIENTE] Error de conexión", flush=True)
                    self.game_client.disconnect()
                    self.game_client = None
                    self.menu_state = "MAIN"
                    self.is_multiplayer = False
        for p in self.menu_particles:
            p["y"] -= p["speed"] * dt
            p["x"] += p["drift"]
            if p["y"] < -5:
                p["y"] = 645
                p["x"] = random.uniform(0, 1024)

        # Mouse hover for menu options
        if hasattr(self, 'menu_state') and self.menu_state == "MAIN":
            mx, my = pygame.mouse.get_pos()
            panel_w, panel_h = 480, 320
            panel_x = (1024 - panel_w) // 2
            panel_y = (640 - panel_h) // 2
            for i in range(len(self.menu_options_list)):
                opt_y = panel_y + 105 + i * 35
                rect = pygame.Rect(512 - 150, opt_y - 15, 300, 30)
                if rect.collidepoint((mx, my)):
                    self.menu_selection = i

    def _update_multiplayer_map(self, dt):
        if not self.game_client:
            return

        # Check connection state
        if self.game_client.state in ("FAILED", "DISCONNECTED"):
            print("[Game] Multiplayer connection lost.")
            self.game_client.disconnect()
            self.game_client = None
            self.is_multiplayer = False
            self.hero = Hero()
            self.map_system = MapSystem(self.hero)
            self.reset_last_sent_state()
            self.state = "MENU"
            self.menu_state = "MAIN"
            self.menu_selection = 0
            return

        # Poll all messages in queue
        while True:
            msg = self.game_client.get_message()
            if not msg:
                break

            mtype = msg.get("type")
            if mtype in ("PLAYER_JOINED", "PLAYER_LEFT", "ROOM_UPDATE"):
                self.room_data = msg.get("room")
                if self.room_data:
                    self.room_code = self.room_data.get("room_code", self.room_code)
                    self._resolve_color_conflict()
            elif mtype == "ERROR":
                print(f"[Game] Server error: {msg.get('message')}")
                self.game_client.disconnect()
                self.game_client = None
                self.is_multiplayer = False
                self.hero = Hero()
                self.map_system = MapSystem(self.hero)
                self.reset_last_sent_state()
                self.state = "MENU"
                self.menu_state = "MAIN"
                self.menu_selection = 0
                return

        # Check and send local player updates
        self.progress_sync_timer += dt
        force_sync = False
        if self.progress_sync_timer >= 3.0:
            self.progress_sync_timer = 0.0
            force_sync = True

        curr_x = self.map_system.pos_x
        curr_y = self.map_system.pos_y
        curr_anim = self.map_system.hero_current_anim
        curr_facing = self.map_system.hero_facing_right
        curr_color = self.hero.hero_color_name
        curr_lvl = self.hero.level
        curr_hp = self.hero.hp
        curr_shield = self.hero.shield
        curr_exp = self.hero.hero_exp

        if (force_sync or
            self.last_sent_pos_x != curr_x or
            self.last_sent_pos_y != curr_y or
            self.last_sent_anim != curr_anim or
            self.last_sent_facing != curr_facing or
            self.last_sent_color != curr_color or
            self.last_sent_lvl != curr_lvl or
            self.last_sent_hp != curr_hp or
            self.last_sent_shield != curr_shield or
            self.last_sent_exp != curr_exp):

            sync_msg = {
                "type": "SYNC_PLAYER",
                "player": {
                    "player_id": self.player_id,
                    "player_name": self.hero.name,
                    "hero_color": curr_color,
                    "hero_level": curr_lvl,
                    "hero_hp": curr_hp,
                    "hero_shield": curr_shield,
                    "position_x": curr_x,
                    "position_y": curr_y,
                    "is_host": self.is_host,
                    "anim_name": curr_anim,
                    "facing_right": curr_facing,
                    "hero_exp": curr_exp
                }
            }
            self.game_client.send_message(sync_msg)

            self.last_sent_pos_x = curr_x
            self.last_sent_pos_y = curr_y
            self.last_sent_anim = curr_anim
            self.last_sent_facing = curr_facing
            self.last_sent_color = curr_color
            self.last_sent_lvl = curr_lvl
            self.last_sent_hp = curr_hp
            self.last_sent_shield = curr_shield
            self.last_sent_exp = curr_exp

    def _draw_menu(self, surface):
        # Draw LOAD_GAME screen if active
        if hasattr(self, 'menu_state') and self.menu_state == "LOAD_GAME":
            self._draw_load_game_screen(surface)
            return
        # Background
        if hasattr(self, 'menu_bg_strip') and self.menu_bg_strip:
            scroll = int(self.menu_scroll) % (1024 + 64)
            surface.blit(self.menu_bg_strip, (-scroll, 0))
            surface.blit(self.menu_bg_strip, (-scroll + 1024 + 64, 0))
        else:
            surface.fill((10, 5, 20))

        # Dim overlay
        dim = pygame.Surface((1024, 640), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 80))
        surface.blit(dim, (0, 0))

        # Particles
        for p in self.menu_particles:
            ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
            a = int(p["alpha"] * (0.6 + 0.4 * math.sin(self.menu_anim_timer * 2 + p["x"])))
            pygame.draw.circle(ps, (255, 220, 100, max(0, min(255, a))),
                               (p["size"], p["size"]), p["size"])
            surface.blit(ps, (int(p["x"]), int(p["y"])))

        # Hero
        hero_y = 320
        if self.menu_hero_frames:
            idx = int((self.menu_anim_timer * 6) % len(self.menu_hero_frames))
            hero_frame = self.menu_hero_frames[idx]
            bob = int(math.sin(self.menu_anim_timer * 2) * 4)
            hero_rect = hero_frame.get_rect(center=(160, hero_y + bob))
            surface.blit(hero_frame, hero_rect)

        # Treant
        if self.menu_treant_frames:
            idx = int((self.menu_anim_timer * 4) % len(self.menu_treant_frames))
            treant_frame = self.menu_treant_frames[idx]
            bob = int(math.sin(self.menu_anim_timer * 1.5 + 1) * 4)
            treant_rect = treant_frame.get_rect(center=(864, hero_y + bob))
            surface.blit(treant_frame, treant_rect)

        # Panel
        panel_w, panel_h = 480, 320
        panel_x = (1024 - panel_w) // 2
        panel_y = (640 - panel_h) // 2
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        for row in range(panel_h):
            a = 200 - int(row / panel_h * 30)
            pygame.draw.line(panel, (8, 6, 25, a), (0, row), (panel_w, row))
        surface.blit(panel, (panel_x, panel_y))
        border_color = (180, 150, 50)
        pygame.draw.rect(surface, border_color, (panel_x, panel_y, panel_w, panel_h), 2)
        corner_len = 15
        for cx, cy, dx, dy in [
            (panel_x, panel_y, 1, 1),
            (panel_x + panel_w - 1, panel_y, -1, 1),
            (panel_x, panel_y + panel_h - 1, 1, -1),
            (panel_x + panel_w - 1, panel_y + panel_h - 1, -1, -1),
        ]:
            pygame.draw.line(surface, (255, 215, 0), (cx, cy), (cx + dx * corner_len, cy), 2)
            pygame.draw.line(surface, (255, 215, 0), (cx, cy), (cx, cy + dy * corner_len), 2)

        # Title
        title_str = "DUNGEON DICE"
        shadow_color = (100, 70, 0)
        title_color = (255, 215, 0)
        shadow_surf = self.font_title.render(title_str, True, shadow_color)
        title_surf = self.font_title.render(title_str, True, title_color)
        title_rect = title_surf.get_rect(center=(512, panel_y + 45))
        surface.blit(shadow_surf, title_rect.move(3, 3))
        surface.blit(shadow_surf, title_rect.move(2, 2))
        surface.blit(title_surf, title_rect)
        line_y = panel_y + 85
        pygame.draw.line(surface, (180, 150, 50, 200), (panel_x + 40, line_y), (panel_x + panel_w - 40, line_y), 1)

        # Options
        option_y = panel_y + 105
        for i, opt in enumerate(self.menu_options_list):
            color = (220, 220, 220)
            if i == self.menu_selection:
                # highlight selected option with a background rectangle
                rect_opt = self.font_medium.render(opt, True, (255, 215, 0)).get_rect(center=(512, option_y))
                bg_rect = pygame.Rect(rect_opt.x - 10, rect_opt.y - 4, rect_opt.width + 20, rect_opt.height + 8)
                pygame.draw.rect(surface, (60, 40, 120), bg_rect)
                color = (255, 215, 0)
            opt_surf = self.font_medium.render(opt, True, color)
            surface.blit(opt_surf, opt_surf.get_rect(center=(512, option_y)))
            option_y += 35

        # Center instruction text
        alpha = int((math.sin(self.menu_anim_timer * 3) + 1) / 2 * 255)
        sub_str = "Presiona ENTER o ESPACIO para seleccionar"
        sub_surf = self.font_small.render(sub_str, True, (200, 200, 200))
        temp = pygame.Surface(sub_surf.get_size(), pygame.SRCALPHA)
        temp.fill((255, 255, 255, alpha))
        sub_surf.blit(temp, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(sub_surf, sub_surf.get_rect(center=(512, panel_y + panel_h - 22)))

        # Draw player name input modal on top if active
        if hasattr(self, 'menu_state') and self.menu_state == "NAME_INPUT":
            # Dark transparent overlay for the modal
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            # Modal Box
            modal_w, modal_h = 420, 310
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            # Title: "Ingresa tu nombre:"
            title_text = self.font_medium.render("Ingresa tu nombre:", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 22))
            
            # Input field representation: [____________]
            input_w, input_h = 320, 40
            input_x = 512 - input_w // 2
            input_y = modal_y + 70
            pygame.draw.rect(surface, (8, 6, 20), (input_x, input_y, input_w, input_h), border_radius=4)
            pygame.draw.rect(surface, (100, 80, 160), (input_x, input_y, input_w, input_h), 1, border_radius=4)
            
            # Render input name with blinking underscore cursor
            cursor = "_" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
            display_name = self.player_name_input + cursor
            name_surf = self.font_medium.render(display_name, True, (255, 255, 255))
            surface.blit(name_surf, (input_x + 10, input_y + (input_h - name_surf.get_height()) // 2))
            
            # Color selection:
            lbl_color = self.font_small.render("Elige tu color:", True, (200, 200, 200))
            surface.blit(lbl_color, (512 - lbl_color.get_width() // 2, modal_y + 125))
            
            circle_y = modal_y + 165
            circle_spacing = 40
            start_cx = 512 - (len(self.colors_available) - 1) * circle_spacing // 2
            for idx, c in enumerate(self.colors_available):
                cx = start_cx + idx * circle_spacing
                pygame.draw.circle(surface, c["rgb"], (cx, circle_y), 12)
                if idx == self.selected_color_idx:
                    pygame.draw.circle(surface, (255, 255, 255), (cx, circle_y), 14, 2)
            
            # Comenzar button: [ Comenzar ]
            btn_w, btn_h = 200, 45
            btn_x = 512 - btn_w // 2
            btn_y = modal_y + 225
            
            mx, my = pygame.mouse.get_pos()
            btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            is_hover = btn_rect.collidepoint((mx, my))
            
            btn_color = (60, 40, 120) if is_hover else (30, 20, 60)
            pygame.draw.rect(surface, btn_color, btn_rect, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50), btn_rect, 2, border_radius=6)
            
            btn_text = self.font_medium.render("Comenzar", True, (255, 215, 0) if is_hover else (220, 220, 220))
            surface.blit(btn_text, (512 - btn_text.get_width() // 2, btn_y + (btn_h - btn_text.get_height()) // 2))

        # Draw LOBBY modal (waiting room for both host and guest)
        elif hasattr(self, 'menu_state') and self.menu_state == "LOBBY":
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            modal_w, modal_h = 560, 420
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            title_text = self.font_medium.render("SALA DE ESPERA", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 25))
            
            code_text = self.font_medium.render(f"Codigo: {self.room_code}", True, (255, 255, 255))
            surface.blit(code_text, (512 - code_text.get_width() // 2, modal_y + 70))
            
            players = []
            if self.room_data and "players" in self.room_data:
                players = list(self.room_data["players"].values())
            
            if not players:
                players = [{
                    "player_id": self.player_id,
                    "player_name": self.hero.name,
                    "hero_color": self.hero.hero_color_name,
                    "is_host": self.is_host
                }]
                
            lbl_players = self.font_small.render("Jugadores conectados:", True, (200, 200, 200))
            surface.blit(lbl_players, (modal_x + 40, modal_y + 120))
            
            py = modal_y + 145
            for p in players:
                p_name = p.get("player_name", "Jugador")
                p_color_name = p.get("hero_color", "Rojo")
                rgb = self._get_color_rgb(p_color_name)
                
                host_suffix = " (Host)" if p.get("is_host") else ""
                p_text = f"- {p_name}{host_suffix}"
                p_surf = self.font_medium.render(p_text, True, rgb)
                surface.blit(p_surf, (modal_x + 50, py))
                py += 28
                
            # Info labels on the left
            lbl_info = self.font_small.render("Haz click en un color disponible", True, (150, 150, 150))
            surface.blit(lbl_info, (modal_x + 40, modal_y + 230))
            lbl_info2 = self.font_small.render("para cambiarlo.", True, (150, 150, 150))
            surface.blit(lbl_info2, (modal_x + 40, modal_y + 245))

            # Activity log on the left
            lbl_activity = self.font_small.render("Actividad:", True, (200, 200, 200))
            surface.blit(lbl_activity, (modal_x + 40, modal_y + 270))
            
            ny = modal_y + 290
            for note_text, t in self.lobby_notifications[-2:]:
                col = (100, 255, 100) if "unido" in note_text else (255, 100, 100)
                note_surf = self.font_small.render(note_text, True, col)
                surface.blit(note_surf, (modal_x + 40, ny))
                ny += 18
            
            # Draw color selection grid on the right side
            lbl_color_select = self.font_small.render("Seleccionar Color:", True, (200, 200, 200))
            surface.blit(lbl_color_select, (modal_x + 280, modal_y + 120))
            
            occupied_map = {}
            for p in players:
                p_id = p.get("player_id")
                p_color = p.get("hero_color")
                p_name = p.get("player_name")
                occupied_map[p_color] = {
                    "player_id": p_id,
                    "player_name": p_name
                }
            
            for idx, c in enumerate(self.colors_available):
                col = idx // 3
                row = idx % 3
                item_x = modal_x + 280 + col * 135
                item_y = modal_y + 150 + row * 45
                
                c_name = c["name"]
                rgb = c["rgb"]
                
                is_own = (c_name == self.hero.hero_color_name)
                is_occupied = (c_name in occupied_map and not is_own)
                
                # Draw hover highlight if available and not own
                mx, my = pygame.mouse.get_pos()
                item_rect = pygame.Rect(item_x - 5, item_y - 2, 125, 40)
                is_hover = item_rect.collidepoint((mx, my)) and not is_occupied and not is_own
                
                if is_hover:
                    pygame.draw.rect(surface, (40, 30, 80), item_rect, border_radius=4)
                    pygame.draw.rect(surface, (15, 10, 30) if is_occupied else (150, 120, 220), item_rect, 1, border_radius=4)
                elif is_own:
                    pygame.draw.rect(surface, (20, 45, 30), item_rect, border_radius=4)
                    pygame.draw.rect(surface, (60, 220, 100), item_rect, 1, border_radius=4)
                
                # Draw color circle
                pygame.draw.circle(surface, rgb, (item_x + 12, item_y + 18), 10)
                if is_own:
                    pygame.draw.circle(surface, (255, 255, 255), (item_x + 12, item_y + 18), 12, 1)
                
                # Render text
                color_lbl = self.font_small.render(c_name, True, (255, 255, 255) if not is_occupied else (100, 100, 100))
                surface.blit(color_lbl, (item_x + 28, item_y + 2))
                
                # Status label
                if is_own:
                    status_lbl = self.font_small.render("Tuyo", True, (60, 220, 100))
                elif is_occupied:
                    status_lbl = self.font_small.render("Ocupado", True, (220, 60, 60))
                else:
                    status_lbl = self.font_small.render("Disponible", True, (160, 160, 160))
                surface.blit(status_lbl, (item_x + 28, item_y + 18))
            
            can_start = len(players) >= 2
            if len(players) < 2:
                status_text = "Esperando jugadores..."
                status_color = (180, 150, 255)
            else:
                if self.is_host:
                    status_text = "¡Sala llena! Listo para comenzar."
                    status_color = (100, 255, 100)
                else:
                    status_text = "Esperando que el host inicie..."
                    status_color = (100, 255, 100)
                    
            status_surf = self.font_small.render(status_text, True, status_color)
            surface.blit(status_surf, (512 - status_surf.get_width() // 2, modal_y + 320))
            
            mx, my = pygame.mouse.get_pos()
            btn_w, btn_h = 160, 40
            
            if self.is_host:
                btn_start_rect = pygame.Rect(322, modal_y + 360, btn_w, btn_h)
                
                hover_start = btn_start_rect.collidepoint((mx, my)) and can_start
                start_bg = (60, 40, 120) if hover_start else (30, 20, 60)
                pygame.draw.rect(surface, start_bg, btn_start_rect, border_radius=6)
                pygame.draw.rect(surface, (180, 150, 50) if can_start else (60, 50, 20), btn_start_rect, 2, border_radius=6)
                
                start_text_color = (255, 215, 0) if hover_start else ((220, 220, 220) if can_start else (100, 100, 100))
                txt_start = self.font_small.render("Comenzar", True, start_text_color)
                surface.blit(txt_start, (322 + (btn_w - txt_start.get_width()) // 2, modal_y + 360 + (btn_h - txt_start.get_height()) // 2))
                
                btn_cancel_rect = pygame.Rect(502, modal_y + 360, btn_w, btn_h)
                hover_cancel = btn_cancel_rect.collidepoint((mx, my))
                cancel_bg = (60, 40, 120) if hover_cancel else (30, 20, 60)
                pygame.draw.rect(surface, cancel_bg, btn_cancel_rect, border_radius=6)
                pygame.draw.rect(surface, (180, 150, 50), btn_cancel_rect, 2, border_radius=6)
                
                txt_cancel = self.font_small.render("Cancelar", True, (255, 255, 255))
                surface.blit(txt_cancel, (502 + (btn_w - txt_cancel.get_width()) // 2, modal_y + 360 + (btn_h - txt_cancel.get_height()) // 2))
            else:
                btn_cancel_rect = pygame.Rect(512 - btn_w // 2, modal_y + 360, btn_w, btn_h)
                hover_cancel = btn_cancel_rect.collidepoint((mx, my))
                cancel_bg = (60, 40, 120) if hover_cancel else (30, 20, 60)
                pygame.draw.rect(surface, cancel_bg, btn_cancel_rect, border_radius=6)
                pygame.draw.rect(surface, (180, 150, 50), btn_cancel_rect, 2, border_radius=6)
                
                txt_cancel = self.font_small.render("Cancelar", True, (255, 255, 255))
                surface.blit(txt_cancel, ((512 - btn_w // 2) + (btn_w - txt_cancel.get_width()) // 2, modal_y + 360 + (btn_h - txt_cancel.get_height()) // 2))

        # Draw JOIN_LOBBY modal
        elif hasattr(self, 'menu_state') and self.menu_state == "JOIN_LOBBY":
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            modal_w, modal_h = 440, 280
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            title_text = self.font_medium.render("UNIRSE A PARTIDA", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 25))
            
            lbl_code = self.font_small.render("Ingresa codigo:", True, (200, 200, 200))
            surface.blit(lbl_code, (512 - lbl_code.get_width() // 2, modal_y + 70))
            
            input_w, input_h = 240, 45
            input_x = 512 - input_w // 2
            input_y = modal_y + 110
            pygame.draw.rect(surface, (8, 6, 20), (input_x, input_y, input_w, input_h), border_radius=4)
            pygame.draw.rect(surface, (100, 80, 160), (input_x, input_y, input_w, input_h), 1, border_radius=4)
            
            cursor = "_" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
            display_code = self.codigo_input + cursor
            code_surf = self.font_medium.render(display_code, True, (255, 255, 255))
            surface.blit(code_surf, (input_x + (input_w - code_surf.get_width()) // 2, input_y + (input_h - code_surf.get_height()) // 2))
            
            # Draw validation error if set
            if hasattr(self, 'room_check_error') and self.room_check_error:
                err_surf = self.font_small.render(self.room_check_error, True, (255, 100, 100))
                surface.blit(err_surf, (512 - err_surf.get_width() // 2, modal_y + 162))

            mx, my = pygame.mouse.get_pos()
            btn_w, btn_h = 140, 45
            
            rect_u = pygame.Rect(362, modal_y + 190, btn_w, btn_h)
            hover_u = rect_u.collidepoint((mx, my))
            code_ok = len(self.codigo_input) == 6
            bg_u = (60, 40, 120) if (hover_u and code_ok) else (30, 20, 60)
            text_col_u = (255, 215, 0) if (hover_u and code_ok) else ((220, 220, 220) if code_ok else (100, 100, 100))
            pygame.draw.rect(surface, bg_u, rect_u, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50) if code_ok else (60, 50, 20), rect_u, 2, border_radius=6)
            txt_u = self.font_small.render("Conectar", True, text_col_u)
            surface.blit(txt_u, (362 + (btn_w - txt_u.get_width()) // 2, modal_y + 190 + (btn_h - txt_u.get_height()) // 2))
            
            rect_x = pygame.Rect(522, modal_y + 190, btn_w, btn_h)
            hover_x = rect_x.collidepoint((mx, my))
            bg_x = (60, 40, 120) if hover_x else (30, 20, 60)
            pygame.draw.rect(surface, bg_x, rect_x, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50), rect_x, 2, border_radius=6)
            txt_x = self.font_small.render("Cancelar", True, (255, 255, 255))
            surface.blit(txt_x, (522 + (btn_w - txt_x.get_width()) // 2, modal_y + 190 + (btn_h - txt_x.get_height()) // 2))

        # Draw CHECKING_ROOM modal
        elif hasattr(self, 'menu_state') and self.menu_state == "CHECKING_ROOM":
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            modal_w, modal_h = 440, 280
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            title_text = self.font_medium.render("BUSCANDO SALA", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 40))
            
            dots = "." * (int(pygame.time.get_ticks() / 400) % 4)
            status_surf = self.font_medium.render("Buscando en el servidor" + dots, True, (180, 150, 255))
            surface.blit(status_surf, (512 - status_surf.get_width() // 2, modal_y + 120))

        # Draw ROOM_FOUND modal
        elif hasattr(self, 'menu_state') and self.menu_state == "ROOM_FOUND":
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            modal_w, modal_h = 440, 280
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            title_text = self.font_medium.render("Sala encontrada", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 40))
            
            code_text = self.font_medium.render(f"Código: {self.room_code}", True, (255, 255, 255))
            surface.blit(code_text, (512 - code_text.get_width() // 2, modal_y + 110))
            
            mx, my = pygame.mouse.get_pos()
            btn_w, btn_h = 140, 45
            
            # Unirse button
            rect_u = pygame.Rect(362, modal_y + 190, btn_w, btn_h)
            hover_u = rect_u.collidepoint((mx, my))
            bg_u = (60, 40, 120) if hover_u else (30, 20, 60)
            pygame.draw.rect(surface, bg_u, rect_u, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50), rect_u, 2, border_radius=6)
            txt_u = self.font_small.render("Unirse", True, (255, 215, 0) if hover_u else (220, 220, 220))
            surface.blit(txt_u, (362 + (btn_w - txt_u.get_width()) // 2, modal_y + 190 + (btn_h - txt_u.get_height()) // 2))
            
            # Cancelar button
            rect_x = pygame.Rect(522, modal_y + 190, btn_w, btn_h)
            hover_x = rect_x.collidepoint((mx, my))
            bg_x = (60, 40, 120) if hover_x else (30, 20, 60)
            pygame.draw.rect(surface, bg_x, rect_x, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50), rect_x, 2, border_radius=6)
            txt_x = self.font_small.render("Cancelar", True, (255, 255, 255))
            surface.blit(txt_x, (522 + (btn_w - txt_x.get_width()) // 2, modal_y + 190 + (btn_h - txt_x.get_height()) // 2))

        # Draw CONNECTING modal
        elif hasattr(self, 'menu_state') and self.menu_state == "CONNECTING":
            modal_overlay = pygame.Surface((1024, 640), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            surface.blit(modal_overlay, (0, 0))
            
            modal_w, modal_h = 440, 280
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2
            
            pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (180, 150, 50), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
            
            title_text = self.font_medium.render("UNIRSE A PARTIDA", True, (255, 215, 0))
            surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 25))
            
            if self.game_client and self.game_client.state == "CONNECTING":
                dots = "." * (int(pygame.time.get_ticks() / 400) % 4)
                status_text = "Conectando al lobby" + dots
                status_surf = self.font_medium.render(status_text, True, (180, 150, 255))
            else:
                status_surf = self.font_medium.render("¡Conexion exitosa!", True, (100, 255, 100))
            surface.blit(status_surf, (512 - status_surf.get_width() // 2, modal_y + 110))
            
            mx, my = pygame.mouse.get_pos()
            btn_w, btn_h = 160, 40
            rect_x = pygame.Rect(432, modal_y + 220, btn_w, btn_h)
            hover_x = rect_x.collidepoint((mx, my))
            bg_x = (60, 40, 120) if hover_x else (30, 20, 60)
            pygame.draw.rect(surface, bg_x, rect_x, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50), rect_x, 2, border_radius=6)
            txt_x = self.font_small.render("Cancelar", True, (255, 255, 255))
            surface.blit(txt_x, (432 + (btn_w - txt_x.get_width()) // 2, modal_y + 220 + (btn_h - txt_x.get_height()) // 2))

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def _handle_events(self):
        if hasattr(self.hero, 'pending_level_ups') and self.hero.pending_level_ups:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
                        self.hero.pending_level_ups.pop(0)
                        self.auto_save()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.hero.pending_level_ups.pop(0)
                    self.auto_save()
            return True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if self.state == "MENU":
                # 1. NAME_INPUT State
                if hasattr(self, 'menu_state') and self.menu_state == "NAME_INPUT":
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.menu_state = "MAIN"
                        elif event.key == pygame.K_BACKSPACE:
                            self.player_name_input = self.player_name_input[:-1]
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            self._handle_name_submitted()
                        elif len(event.unicode) > 0 and event.unicode.isprintable():
                            if len(self.player_name_input) < 20:
                                char = event.unicode
                                if char.isalnum() or char == " ":
                                    self.player_name_input += char
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        modal_h = 310
                        modal_y = (640 - modal_h) // 2
                        
                        # Check click on color circles
                        circle_y = modal_y + 165
                        circle_spacing = 40
                        start_cx = 512 - (len(self.colors_available) - 1) * circle_spacing // 2
                        for idx in range(len(self.colors_available)):
                            cx = start_cx + idx * circle_spacing
                            if math.hypot(event.pos[0] - cx, event.pos[1] - circle_y) <= 15:
                                self.selected_color_idx = idx
                                break
                                
                        # Check "Comenzar" click
                        btn_w, btn_h = 200, 45
                        btn_x = 512 - btn_w // 2
                        btn_y = modal_y + 225
                        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
                        if btn_rect.collidepoint(event.pos):
                            self._handle_name_submitted()
                    continue

                # LOBBY State (host & guest connected)
                elif hasattr(self, 'menu_state') and self.menu_state == "LOBBY":
                    players = []
                    if self.room_data and "players" in self.room_data:
                        players = list(self.room_data["players"].values())
                        
                    modal_y = (640 - 420) // 2
                    
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            if self.game_client:
                                self.game_client.disconnect()
                                self.game_client = None
                            self.menu_state = "MAIN"
                            self.is_multiplayer = False
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            if self.is_host and len(players) >= 2:
                                self.game_client.send_message({"type": "START_GAME"})
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # Check color clicks
                        modal_x = (1024 - 560) // 2
                        modal_y = (640 - 420) // 2
                        occupied_colors = [p.get("hero_color") for p in players if p.get("player_id") != self.player_id]
                        
                        color_clicked = False
                        for idx, c in enumerate(self.colors_available):
                            col = idx // 3
                            row = idx % 3
                            item_x = modal_x + 280 + col * 135
                            item_y = modal_y + 150 + row * 45
                            
                            item_rect = pygame.Rect(item_x - 5, item_y - 2, 125, 40)
                            if item_rect.collidepoint(event.pos):
                                color_clicked = True
                                if c["name"] not in occupied_colors and c["name"] != self.hero.hero_color_name:
                                    self.hero.hero_color_name = c["name"]
                                    self.hero.hero_color_rgb = c["rgb"]
                                    self.auto_save()
                                    sync_msg = {
                                        "type": "SYNC_PLAYER",
                                        "player": {
                                            "player_id": self.player_id,
                                            "player_name": self.hero.name,
                                            "hero_color": self.hero.hero_color_name,
                                            "hero_level": self.hero.level,
                                            "hero_hp": self.hero.hp,
                                            "hero_shield": self.hero.shield,
                                            "position_x": 0.0,
                                            "position_y": 0.0,
                                            "is_host": self.is_host,
                                            "hero_exp": self.hero.hero_exp
                                        }
                                    }
                                    self.game_client.send_message(sync_msg)
                                break
                                
                        if color_clicked:
                            continue
                            
                        btn_w, btn_h = 160, 40
                        if self.is_host:
                            btn_start = pygame.Rect(322, modal_y + 360, btn_w, btn_h)
                            btn_cancel = pygame.Rect(502, modal_y + 360, btn_w, btn_h)
                            if btn_start.collidepoint(event.pos) and len(players) >= 2:
                                self.game_client.send_message({"type": "START_GAME"})
                            elif btn_cancel.collidepoint(event.pos):
                                self.game_client.disconnect()
                                self.game_client = None
                                self.menu_state = "MAIN"
                                self.is_multiplayer = False
                        else:
                            btn_cancel = pygame.Rect(512 - btn_w // 2, modal_y + 360, btn_w, btn_h)
                            if btn_cancel.collidepoint(event.pos):
                                self.game_client.disconnect()
                                self.game_client = None
                                self.menu_state = "MAIN"
                                self.is_multiplayer = False
                    continue

                # JOIN_LOBBY State
                elif hasattr(self, 'menu_state') and self.menu_state == "JOIN_LOBBY":
                    modal_y = (640 - 280) // 2
                    if event.type == pygame.KEYDOWN:
                        self.room_check_error = "" # Clear error on typing
                        if event.key == pygame.K_ESCAPE:
                            self.menu_state = "MAIN"
                            self.is_multiplayer = False
                        elif event.key == pygame.K_BACKSPACE:
                            self.codigo_input = self.codigo_input[:-1]
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            if len(self.codigo_input) == 6:
                                self._start_check_room(self.codigo_input)
                        elif len(event.unicode) > 0 and event.unicode.isprintable():
                            if len(self.codigo_input) < 6:
                                char = event.unicode.upper()
                                if char.isalnum():
                                    self.codigo_input += char
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        btn_unirse = pygame.Rect(362, modal_y + 190, 140, 45)
                        btn_cancelar = pygame.Rect(522, modal_y + 190, 140, 45)
                        if btn_unirse.collidepoint(event.pos):
                            if len(self.codigo_input) == 6:
                                self._start_check_room(self.codigo_input)
                        elif btn_cancelar.collidepoint(event.pos):
                            self.menu_state = "MAIN"
                            self.is_multiplayer = False
                    continue

                # ROOM_FOUND State
                elif hasattr(self, 'menu_state') and self.menu_state == "ROOM_FOUND":
                    modal_y = (640 - 280) // 2
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.menu_state = "JOIN_LOBBY"
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            print("[CLIENTE] Intentando conectar", flush=True)
                            self.game_client = GameClient()
                            self.game_client.connect(self.room_code, self.player_id, self.hero.name)
                            self.has_synced_initial_player = False
                            self.room_data = None
                            self.menu_state = "CONNECTING"
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        btn_w, btn_h = 140, 45
                        btn_unirse = pygame.Rect(362, modal_y + 190, btn_w, btn_h)
                        btn_cancelar = pygame.Rect(522, modal_y + 190, btn_w, btn_h)
                        if btn_unirse.collidepoint(event.pos):
                            print("[CLIENTE] Intentando conectar", flush=True)
                            self.game_client = GameClient()
                            self.game_client.connect(self.room_code, self.player_id, self.hero.name)
                            self.has_synced_initial_player = False
                            self.room_data = None
                            self.menu_state = "CONNECTING"
                        elif btn_cancelar.collidepoint(event.pos):
                            self.menu_state = "JOIN_LOBBY"
                    continue

                # CONNECTING State
                elif hasattr(self, 'menu_state') and self.menu_state == "CONNECTING":
                    modal_y = (640 - 280) // 2
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            if self.game_client:
                                self.game_client.disconnect()
                                self.game_client = None
                            self.menu_state = "MAIN"
                            self.is_multiplayer = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        btn_cancel = pygame.Rect(432, modal_y + 220, 160, 40)
                        if btn_cancel.collidepoint(event.pos):
                            if self.game_client:
                                self.game_client.disconnect()
                                self.game_client = None
                            self.menu_state = "MAIN"
                            self.is_multiplayer = False
                    continue

                # 5. LOAD_GAME State
                elif hasattr(self, 'menu_state') and self.menu_state == "LOAD_GAME":
                    if self.confirm_delete_save is not None:
                        # Event handling for delete confirmation overlay
                        if event.type == pygame.KEYDOWN:
                            if event.key in (pygame.K_s, pygame.K_y): # Sí / Yes
                                self._delete_save(self.confirm_delete_save)
                            elif event.key in (pygame.K_n, pygame.K_ESCAPE): # No
                                self.confirm_delete_save = None
                        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            modal_w, modal_h = 340, 160
                            modal_x = (1024 - modal_w) // 2
                            modal_y = (640 - modal_h) // 2
                            btn_w, btn_h = 100, 35
                            btn_si = pygame.Rect(modal_x + 40, modal_y + 100, btn_w, btn_h)
                            btn_no = pygame.Rect(modal_x + 200, modal_y + 100, btn_w, btn_h)
                            if btn_si.collidepoint(event.pos):
                                self._delete_save(self.confirm_delete_save)
                            elif btn_no.collidepoint(event.pos):
                                self.confirm_delete_save = None
                        continue

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.menu_state = "MAIN"
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # [ Volver ] button at top-left
                        btn_back = pygame.Rect(30, 30, 100, 35)
                        if btn_back.collidepoint(event.pos):
                            self.menu_state = "MAIN"
                            continue
                            
                        # Paging controls
                        total_pages = math.ceil(len(self.saved_games) / 6)
                        if total_pages > 1:
                            btn_prev = pygame.Rect(300, 560, 120, 35)
                            btn_next = pygame.Rect(604, 560, 120, 35)
                            if btn_prev.collidepoint(event.pos) and self.load_page > 0:
                                self.load_page -= 1
                            elif btn_next.collidepoint(event.pos) and self.load_page < total_pages - 1:
                                self.load_page += 1
                                
                        # Check cards actions
                        start_idx = self.load_page * 6
                        page_saves = self.saved_games[start_idx : start_idx + 6]
                        
                        card_w, card_h = 280, 180
                        cols_x = [62, 372, 682]
                        rows_y = [100, 310]
                        
                        for idx, save_data in enumerate(page_saves):
                            col_idx = idx % 3
                            row_idx = idx // 3
                            bx = cols_x[col_idx]
                            by = rows_y[row_idx]
                            
                            # [ Cargar ] button
                            btn_load = pygame.Rect(bx + 15, by + 135, 115, 32)
                            # [ Eliminar ] button
                            btn_del = pygame.Rect(bx + 150, by + 135, 115, 32)
                            
                            if btn_load.collidepoint(event.pos):
                                self._load_save(save_data)
                                break
                            elif btn_del.collidepoint(event.pos):
                                self.confirm_delete_save = save_data
                                break
                    continue

                # MAIN MENU Navigation
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.menu_selection = (self.menu_selection - 1) % len(self.menu_options_list)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.menu_selection = (self.menu_selection + 1) % len(self.menu_options_list)
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        self._process_menu_selection()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    panel_w, panel_h = 480, 320
                    panel_y = (640 - panel_h) // 2
                    hovered = False
                    for i in range(len(self.menu_options_list)):
                        opt_y = panel_y + 105 + i * 35
                        rect = pygame.Rect(512 - 150, opt_y - 15, 300, 30)
                        if rect.collidepoint((mx, my)):
                            self.menu_selection = i
                            hovered = True
                            break
                    if hovered:
                        self._process_menu_selection()
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
            if self.state == "BATTLE":
                self.battle.handle_event(event)
            elif self.state == "BATTLE_VICTORY":
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.auto_save()
                        self.battle = None
                        self.state = "MAP"
                        continue
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    modal_y = (640 - 320) // 2
                    btn_cont = pygame.Rect(332, modal_y + 245, 160, 40)
                    btn_rep = pygame.Rect(532, modal_y + 245, 160, 40)
                    if btn_cont.collidepoint(event.pos):
                        self.auto_save()
                        self.battle = None
                        self.state = "MAP"
                        continue
                    elif btn_rep.collidepoint(event.pos):
                        same_level = getattr(self, "last_defeated_enemy_level", 1)
                        if random.random() < 0.5:
                            lvl = same_level
                        else:
                            lvl = max(1, self.hero.level + random.choice([-1, 0, 1]))
                        from engine.entities import Enemy
                        self.start_battle(Enemy(level=lvl))
                        continue
            elif self.state == "MAP":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    # Escape only returns to menu if no map overlays are active
                    if not (self.map_system.show_encounter_panel or 
                            self.map_system.show_sanctuary_panel or 
                            self.map_system.sanctuary_minigame is not None):
                        self.auto_save()
                        self.hero = Hero()
                        self.map_system = MapSystem(self.hero)
                        self.state = "MENU"
                        self.menu_state = "MAIN"
                        self.menu_selection = 0
                        continue
                encounter = self.map_system.handle_event(event)
                if encounter:
                    self.start_battle(encounter)
            elif self.state == "GAME_OVER":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.hero = Hero()
                    self.map_system = MapSystem(self.hero)
                    self.battle = None
                    self.state = "MENU"
                    self.menu_state = "MAIN"
                    self.menu_selection = 0
        return True

    def _process_menu_selection(self):
        """Handle menu selection based on current highlight."""
        option = self.menu_options_list[self.menu_selection]
        if option == "NUEVA PARTIDA" or option == "INICIAR NUEVA PARTIDA":
            self.menu_state = "NAME_INPUT"
            self.name_input_target_state = "NUEVA_PARTIDA"
            self.player_name_input = ""
        elif option == "CARGAR PARTIDA":
            self.menu_state = "LOAD_GAME"
            self.load_page = 0
            self.confirm_delete_save = None
            from engine.save import get_all_saves
            self.saved_games = get_all_saves()
        elif option == "CREAR PARTIDA":
            self.menu_state = "NAME_INPUT"
            self.name_input_target_state = "CREAR_PARTIDA"
            self.player_name_input = ""
        elif option == "UNIRSE A PARTIDA":
            self.menu_state = "NAME_INPUT"
            self.name_input_target_state = "UNIRSE_PARTIDA"
            self.player_name_input = ""
        elif option == "SALIR":
            pygame.quit()
            sys.exit()

    def _handle_name_submitted(self):
        name = self.player_name_input.strip()
        if not name:
            return
        
        chosen_color = self.colors_available[self.selected_color_idx]
        import datetime
        import time
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
        # Setup unique save file path
        save_path = os.path.join("saves", f"save_{int(time.time())}.json")
        
        if self.name_input_target_state == "NUEVA_PARTIDA":
            self.is_multiplayer = False
            self.hero = Hero()
            self.hero.name = name
            self.hero.hero_color_name = chosen_color["name"]
            self.hero.hero_color_rgb = chosen_color["rgb"]
            self.hero.creation_date = now_str
            self.hero.last_saved_date = now_str
            self.hero.play_time = 0.0
            self.hero.current_save_path = save_path
            
            self.map_system = MapSystem(self.hero)
            self.auto_save()
            
            self.state = "MAP"
            self.menu_state = "MAIN"
            
        elif self.name_input_target_state == "CREAR_PARTIDA":
            self.is_multiplayer = True
            self.hero = Hero()
            self.hero.name = name
            self.hero.hero_color_name = chosen_color["name"]
            self.hero.hero_color_rgb = chosen_color["rgb"]
            self.hero.creation_date = now_str
            self.hero.last_saved_date = now_str
            self.hero.play_time = 0.0
            self.hero.current_save_path = save_path
            
            self.map_system = MapSystem(self.hero)
            self.auto_save()
            self.reset_last_sent_state()
            
            self.is_host = True
            self.player_id = f"player_{int(time.time())}_{random.randint(1000, 9999)}"
            self.room_code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            
            self.game_client = GameClient()
            self.game_client.connect(self.room_code, self.player_id, name)
            self.has_synced_initial_player = False
            self.room_data = None
            
            self.menu_state = "LOBBY"
            
        elif self.name_input_target_state == "UNIRSE_PARTIDA":
            self.is_multiplayer = True
            self.hero = Hero()
            self.hero.name = name
            self.hero.hero_color_name = chosen_color["name"]
            self.hero.hero_color_rgb = chosen_color["rgb"]
            self.hero.creation_date = now_str
            self.hero.last_saved_date = now_str
            self.hero.play_time = 0.0
            self.hero.current_save_path = save_path
            
            self.map_system = MapSystem(self.hero)
            self.auto_save()
            self.reset_last_sent_state()
            
            self.is_host = False
            self.player_id = f"player_{int(time.time())}_{random.randint(1000, 9999)}"
            self.codigo_input = ""
            
            self.menu_state = "JOIN_LOBBY"

    def _load_save(self, save_data):
        self.hero.load_data(save_data)
        self.map_system = MapSystem(self.hero)
        if "pos_x" in save_data:
            self.map_system.pos_x = float(save_data["pos_x"])
        if "pos_y" in save_data:
            self.map_system.pos_y = float(save_data["pos_y"])
        if "camera_x" in save_data:
            self.map_system.camera_x = float(save_data["camera_x"])
        if "camera_y" in save_data:
            self.map_system.camera_y = float(save_data["camera_y"])
        if "map_steps" in save_data:
            self.map_system.steps = int(save_data["map_steps"])
        self.map_system._clamp_camera()
        self.state = "MAP"
        self.menu_state = "MAIN"

    def _delete_save(self, save_data):
        filepath = save_data.get("_filepath")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting save file {filepath}: {e}")
        self.confirm_delete_save = None
        from engine.save import get_all_saves
        self.saved_games = get_all_saves()
        total_pages = math.ceil(len(self.saved_games) / 6)
        if self.load_page >= total_pages and self.load_page > 0:
            self.load_page = total_pages - 1

    def _draw_load_game_screen(self, surface):
        # Background
        if hasattr(self, 'menu_bg_strip') and self.menu_bg_strip:
            scroll = int(self.menu_scroll) % (1024 + 64)
            surface.blit(self.menu_bg_strip, (-scroll, 0))
            surface.blit(self.menu_bg_strip, (-scroll + 1024 + 64, 0))
        else:
            surface.fill((10, 5, 20))

        # Dim overlay
        dim = pygame.Surface((1024, 640), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 80))
        surface.blit(dim, (0, 0))

        # Particles
        for p in self.menu_particles:
            ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
            a = int(p["alpha"] * (0.6 + 0.4 * math.sin(self.menu_anim_timer * 2 + p["x"])))
            pygame.draw.circle(ps, (255, 220, 100, max(0, min(255, a))),
                               (p["size"], p["size"]), p["size"])
            surface.blit(ps, (int(p["x"]), int(p["y"])))

        mx, my = pygame.mouse.get_pos()

        # Title
        title_text = self.font_large.render("CARGAR PARTIDA", True, (255, 215, 0))
        surface.blit(title_text, (512 - title_text.get_width() // 2, 30))

        # [ Volver ] button
        btn_back = pygame.Rect(30, 30, 100, 35)
        hover_back = btn_back.collidepoint((mx, my))
        bg_back = (60, 40, 120) if hover_back else (30, 20, 60)
        pygame.draw.rect(surface, bg_back, btn_back, border_radius=6)
        pygame.draw.rect(surface, (180, 150, 50), btn_back, 2, border_radius=6)
        txt_back = self.font_small.render("Volver", True, (255, 215, 0) if hover_back else (220, 220, 220))
        surface.blit(txt_back, (30 + (100 - txt_back.get_width()) // 2, 30 + (35 - txt_back.get_height()) // 2))

        # If empty
        if not self.saved_games:
            txt_empty = self.font_medium.render("No hay partidas guardadas.", True, (180, 180, 180))
            surface.blit(txt_empty, (512 - txt_empty.get_width() // 2, 320 - txt_empty.get_height() // 2))
            return

        # Paged Grid of Cards
        total_pages = math.ceil(len(self.saved_games) / 6)
        start_idx = self.load_page * 6
        page_saves = self.saved_games[start_idx : start_idx + 6]

        card_w, card_h = 280, 180
        cols_x = [62, 372, 682]
        rows_y = [100, 310]

        for idx, save_data in enumerate(page_saves):
            col_idx = idx % 3
            row_idx = idx // 3
            bx = cols_x[col_idx]
            by = rows_y[row_idx]

            # Hover detection
            card_rect = pygame.Rect(bx, by, card_w, card_h)
            is_card_hover = card_rect.collidepoint((mx, my))

            card_bg = (20, 15, 40, 230) if is_card_hover else (12, 8, 26, 200)
            card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            pygame.draw.rect(card_surf, card_bg, (0, 0, card_w, card_h), border_radius=6)
            pygame.draw.rect(card_surf, (180, 150, 50) if is_card_hover else (80, 60, 140), (0, 0, card_w, card_h), 2, border_radius=6)
            surface.blit(card_surf, (bx, by))

            # Color choice and Hero Name
            color_rgb = save_data.get("hero_color_rgb", (220, 60, 60))
            color_rgb = (max(0, min(255, color_rgb[0])), max(0, min(255, color_rgb[1])), max(0, min(255, color_rgb[2])))
            name_str = save_data.get("name", "Héroe")
            name_surf = self.font_medium.render(name_str, True, color_rgb)
            surface.blit(name_surf, (bx + 15, by + 12))

            # Color dot indicator
            pygame.draw.circle(surface, color_rgb, (bx + card_w - 20, by + 22), 6)

            # Divider
            pygame.draw.line(surface, (80, 60, 140), (bx + 15, by + 36), (bx + card_w - 15, by + 36), 1)

            # Stats lines
            lvl = save_data.get("hero_level", save_data.get("level", 1))
            exp = save_data.get("hero_exp", 0)
            to_next = save_data.get("exp_to_next_level", lvl * 100)
            hp = save_data.get("hp", 50)
            mhp = save_data.get("max_hp", 50)
            shld = save_data.get("shield", 0)
            mshld = save_data.get("max_shield", 20)

            stats_line1 = f"Nivel {lvl}  |  EXP {exp}/{to_next}"
            stats_line2 = f"HP {hp}/{mhp}  |  Escudo {shld}/{mshld}"

            txt_s1 = self.font_small.render(stats_line1, True, (220, 220, 220))
            txt_s2 = self.font_small.render(stats_line2, True, (220, 220, 220))
            surface.blit(txt_s1, (bx + 15, by + 42))
            surface.blit(txt_s2, (bx + 15, by + 60))

            # Dates and play time
            created = save_data.get("creation_date", "N/A")
            saved = save_data.get("last_saved_date", "N/A")
            ptime = save_data.get("play_time", 0.0)

            def format_time(seconds):
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                if h > 0:
                    return f"{h}h {m}m {s}s"
                elif m > 0:
                    return f"{m}m {s}s"
                else:
                    return f"{s}s"

            txt_created = self.font_small.render(f"Creado: {created}", True, (160, 160, 180))
            txt_saved = self.font_small.render(f"Guardado: {saved}", True, (160, 160, 180))
            txt_time = self.font_small.render(f"Tiempo: {format_time(ptime)}", True, (160, 160, 180))

            surface.blit(txt_created, (bx + 15, by + 78))
            surface.blit(txt_saved, (bx + 15, by + 96))
            surface.blit(txt_time, (bx + 15, by + 114))

            # [ Cargar ] Button
            btn_load = pygame.Rect(bx + 15, by + 135, 115, 32)
            hover_load = btn_load.collidepoint((mx, my))
            bg_load = (50, 120, 60) if hover_load else (20, 60, 30)
            pygame.draw.rect(surface, bg_load, btn_load, border_radius=4)
            pygame.draw.rect(surface, (100, 220, 120) if hover_load else (40, 120, 60), btn_load, 1, border_radius=4)
            txt_load = self.font_small.render("Cargar", True, (255, 255, 255))
            surface.blit(txt_load, (bx + 15 + (115 - txt_load.get_width()) // 2, by + 135 + (32 - txt_load.get_height()) // 2))

            # [ Eliminar ] Button
            btn_del = pygame.Rect(bx + 150, by + 135, 115, 32)
            hover_del = btn_del.collidepoint((mx, my))
            bg_del = (140, 40, 40) if hover_del else (70, 20, 20)
            pygame.draw.rect(surface, bg_del, btn_del, border_radius=4)
            pygame.draw.rect(surface, (255, 100, 100) if hover_del else (140, 40, 40), btn_del, 1, border_radius=4)
            txt_del = self.font_small.render("Eliminar", True, (255, 255, 255))
            surface.blit(txt_del, (bx + 150 + (115 - txt_del.get_width()) // 2, by + 135 + (32 - txt_del.get_height()) // 2))

        # Bottom paging controls
        if total_pages > 1:
            # Anterior Button
            btn_prev = pygame.Rect(300, 560, 120, 35)
            hover_prev = btn_prev.collidepoint((mx, my)) and self.load_page > 0
            if self.load_page > 0:
                bg_prev = (60, 40, 120) if hover_prev else (30, 20, 60)
                border_prev = (180, 150, 50)
                txt_color_prev = (255, 215, 0) if hover_prev else (220, 220, 220)
            else:
                bg_prev = (20, 15, 30)
                border_prev = (50, 40, 70)
                txt_color_prev = (100, 100, 100)
            pygame.draw.rect(surface, bg_prev, btn_prev, border_radius=6)
            pygame.draw.rect(surface, border_prev, btn_prev, 2, border_radius=6)
            txt_prev = self.font_small.render("Anterior", True, txt_color_prev)
            surface.blit(txt_prev, (300 + (120 - txt_prev.get_width()) // 2, 560 + (35 - txt_prev.get_height()) // 2))

            # Siguiente Button
            btn_next = pygame.Rect(604, 560, 120, 35)
            hover_next = btn_next.collidepoint((mx, my)) and self.load_page < total_pages - 1
            if self.load_page < total_pages - 1:
                bg_next = (60, 40, 120) if hover_next else (30, 20, 60)
                border_next = (180, 150, 50)
                txt_color_next = (255, 215, 0) if hover_next else (220, 220, 220)
            else:
                bg_next = (20, 15, 30)
                border_next = (50, 40, 70)
                txt_color_next = (100, 100, 100)
            pygame.draw.rect(surface, bg_next, btn_next, border_radius=6)
            pygame.draw.rect(surface, border_next, btn_next, 2, border_radius=6)
            txt_next = self.font_small.render("Siguiente", True, txt_color_next)
            surface.blit(txt_next, (604 + (120 - txt_next.get_width()) // 2, 560 + (35 - txt_next.get_height()) // 2))

            # Page index
            page_str = f"Página {self.load_page + 1} / {total_pages}"
            txt_page = self.font_medium.render(page_str, True, (220, 220, 220))
            surface.blit(txt_page, (512 - txt_page.get_width() // 2, 560 + (35 - txt_page.get_height()) // 2))

        # Delete confirmation overlay
        if self.confirm_delete_save is not None:
            # Dim whole screen
            dim_del = pygame.Surface((1024, 640), pygame.SRCALPHA)
            dim_del.fill((0, 0, 0, 180))
            surface.blit(dim_del, (0, 0))

            # Modal Box
            modal_w, modal_h = 340, 160
            modal_x = (1024 - modal_w) // 2
            modal_y = (640 - modal_h) // 2

            pygame.draw.rect(surface, (20, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
            pygame.draw.rect(surface, (220, 60, 60), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)

            # Text
            msg = self.font_medium.render("¿Eliminar esta partida?", True, (255, 255, 255))
            surface.blit(msg, (512 - msg.get_width() // 2, modal_y + 30))

            # Sí / No Buttons
            btn_w, btn_h = 100, 35
            btn_si = pygame.Rect(modal_x + 40, modal_y + 100, btn_w, btn_h)
            btn_no = pygame.Rect(modal_x + 200, modal_y + 100, btn_w, btn_h)

            hover_si = btn_si.collidepoint((mx, my))
            hover_no = btn_no.collidepoint((mx, my))

            bg_si = (160, 40, 40) if hover_si else (100, 20, 20)
            bg_no = (60, 40, 120) if hover_no else (30, 20, 60)

            # Draw Sí button
            pygame.draw.rect(surface, bg_si, btn_si, border_radius=6)
            pygame.draw.rect(surface, (255, 100, 100) if hover_si else (160, 40, 40), btn_si, 1, border_radius=6)
            txt_si = self.font_small.render("Sí", True, (255, 255, 255))
            surface.blit(txt_si, (modal_x + 40 + (btn_w - txt_si.get_width()) // 2, modal_y + 100 + (btn_h - txt_si.get_height()) // 2))

            # Draw No button
            pygame.draw.rect(surface, bg_no, btn_no, border_radius=6)
            pygame.draw.rect(surface, (180, 150, 50) if hover_no else (80, 60, 140), btn_no, 1, border_radius=6)
            txt_no = self.font_small.render("No", True, (255, 255, 255))
            surface.blit(txt_no, (modal_x + 200 + (btn_w - txt_no.get_width()) // 2, modal_y + 100 + (btn_h - txt_no.get_height()) // 2))

    def _draw_victory_screen(self, surface):
        # Dim whole screen
        dim = pygame.Surface((1024, 640), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        surface.blit(dim, (0, 0))

        # Modal Box
        modal_w, modal_h = 420, 320
        modal_x = (1024 - modal_w) // 2
        modal_y = (640 - modal_h) // 2

        # Background panel
        pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
        pygame.draw.rect(surface, (255, 215, 0), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)

        # Title: MONSTRUO DERROTADO
        pulse = abs(math.sin(pygame.time.get_ticks() / 200.0))
        title_color = (255, 215 + int(40 * pulse), 100)
        title_text = self.font_large.render("MONSTRUO DERROTADO", True, title_color)
        surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 35))

        pygame.draw.line(surface, (100, 80, 160), (modal_x + 30, modal_y + 80), (modal_x + modal_w - 30, modal_y + 80), 1)

        # Stats to show
        enemy_name = getattr(self, "last_defeated_enemy_name", "Monstruo")
        enemy_lvl = getattr(self, "last_defeated_enemy_level", 1)

        txt_name = self.font_medium.render(f"Monstruo: {enemy_name}", True, (255, 255, 255))
        txt_lvl = self.font_medium.render(f"Nivel: {enemy_lvl}", True, (220, 220, 220))
        txt_exp = self.font_medium.render("EXP obtenida: +25 EXP", True, (255, 215, 0))
        txt_hp = self.font_medium.render("Recompensa: +20 HP", True, (100, 255, 100))

        surface.blit(txt_name, (512 - txt_name.get_width() // 2, modal_y + 95))
        surface.blit(txt_lvl, (512 - txt_lvl.get_width() // 2, modal_y + 130))
        surface.blit(txt_exp, (512 - txt_exp.get_width() // 2, modal_y + 165))
        surface.blit(txt_hp, (512 - txt_hp.get_width() // 2, modal_y + 200))

        # Buttons: [ Continuar ] and [ Repetir Combate ]
        btn_w, btn_h = 160, 40
        btn_cont = pygame.Rect(332, modal_y + 245, 160, 40)
        btn_rep = pygame.Rect(532, modal_y + 245, 160, 40)

        mx, my = pygame.mouse.get_pos()
        hover_cont = btn_cont.collidepoint((mx, my))
        hover_rep = btn_rep.collidepoint((mx, my))

        bg_cont = (40, 100, 50) if hover_cont else (20, 60, 30)
        bg_rep = (60, 40, 120) if hover_rep else (30, 20, 60)

        # Continuar button
        pygame.draw.rect(surface, bg_cont, btn_cont, border_radius=6)
        pygame.draw.rect(surface, (100, 220, 120) if hover_cont else (40, 120, 60), btn_cont, 2, border_radius=6)
        txt_cont = self.font_small.render("Continuar", True, (255, 255, 255))
        surface.blit(txt_cont, (332 + (160 - txt_cont.get_width()) // 2, modal_y + 245 + (40 - txt_cont.get_height()) // 2))

        # Repetir Combate button
        pygame.draw.rect(surface, bg_rep, btn_rep, border_radius=6)
        pygame.draw.rect(surface, (180, 150, 55) if hover_rep else (80, 60, 140), btn_rep, 2, border_radius=6)
        txt_rep = self.font_small.render("Repetir Combate", True, (255, 255, 255))
        surface.blit(txt_rep, (532 + (160 - txt_rep.get_width()) // 2, modal_y + 245 + (40 - txt_rep.get_height()) // 2))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        logical = pygame.Surface((1024, 640))
        running = True
        self.last_logged_state = None
        while running:
            # Debug state logging
            if self.state == "MENU":
                current_log_state = "LOAD_GAME" if self.menu_state == "LOAD_GAME" else "MENU"
            else:
                current_log_state = self.state
            if current_log_state != self.last_logged_state:
                print(f"Estado actual: {current_log_state}")
                self.last_logged_state = current_log_state
            dt = clock.tick(FPS) / 1000.0
            if self.state in ("MAP", "BATTLE"):
                self.hero.play_time += dt

            if not self._handle_events():
                running = False

            # update per state
            if self.state == "BATTLE" and self.battle is not None:
                self.battle.update(dt)

                if self.battle.exit_to_menu:
                    self.auto_save()
                    self.battle = None
                    self.hero = Hero()
                    self.map_system = MapSystem(self.hero)
                    self.state = "MENU"
                    self.menu_state = "MAIN"
                    self.menu_selection = 0

                elif self.battle.restart_game:
                    self.battle = None
                    self.hero = Hero()
                    self.map_system = MapSystem(self.hero)
                    self.state = "MAP"

                elif self.battle.is_over():
                    if self.hero.hp <= 0:
                        self.state = "GAME_OVER"
                    else:
                        self.hero.hp = min(self.hero.max_hp, self.hero.hp + 20)
                        self.hero.add_exp(25)
                        self.last_defeated_enemy_name = self.battle.enemy.name
                        self.last_defeated_enemy_level = self.battle.enemy.level
                        self.state = "BATTLE_VICTORY"
            elif self.state == "MAP":
                # Track whether a sanctuary minigame was active before update
                _sanc_was_active = getattr(self.map_system, "sanctuary_minigame", None) is not None
                self.map_system.update()
                if self.is_multiplayer:
                    self._update_multiplayer_map(dt)
                # If minigame just finished → save (rewards + completed list persist)
                _sanc_now_active = getattr(self.map_system, "sanctuary_minigame", None) is not None
                if _sanc_was_active and not _sanc_now_active:
                    self.auto_save()
                if getattr(self.map_system, "pending_encounter", False):
                    self.map_system.pending_encounter = False
                    from engine.entities import Enemy
                    enemy_level = self.hero.level
                    last_type = getattr(self.map_system, "last_collided_type", None)
                    if last_type == "treant":
                        if enemy_level % 2 != 0:
                            enemy_level += 1
                    elif last_type == "mole":
                        if enemy_level % 2 == 0:
                            enemy_level += 1
                    self.start_battle(Enemy(level=enemy_level))
            elif self.state == "MENU":
                self._update_menu(dt)

            self.draw(logical)
            pygame.display.flip()

        self.auto_save()
        pygame.quit()
        sys.exit()

    def draw(self, logical):
        if self.state == "MENU":
            self._draw_menu(logical)
        elif self.state == "MULTI_MENU":
            logical.fill((20, 20, 30))
            text = self.font_large.render("PROXIMAMENTE", True, (255, 200, 0))
            logical.blit(text, (512 - text.get_width() // 2, 320 - text.get_height() // 2))
        else:
            logical.fill((20, 20, 30))
            if self.state == "BATTLE":
                self.battle.draw(logical, self.font_small, self.font_medium, self.font_large)
            elif self.state == "BATTLE_VICTORY":
                if self.battle is not None:
                    self.battle.draw(logical, self.font_small, self.font_medium, self.font_large)
                self._draw_victory_screen(logical)
            elif self.state == "MAP":
                self.map_system.draw(logical, self.font_medium, self.room_data, self.player_id)
            elif self.state == "GAME_OVER":
                logical.fill((10, 5, 20))
                text = self.font_large.render("FIN DEL JUEGO", True, (220, 50, 50))
                logical.blit(text, (512 - text.get_width() // 2, 260))
                sub = self.font_medium.render(
                    "Haz click para volver al menu", True, (180, 150, 255)
                )
                logical.blit(sub, (512 - sub.get_width() // 2, 320))

            # Right side rules panel
            pygame.draw.rect(logical, (12, 8, 25), (884, 0, 140, 640))
            pygame.draw.rect(logical, (80, 60, 160), (884, 0, 140, 640), 2)
            pygame.draw.line(logical, (80, 60, 160), (889, 45), (1020, 45), 1)
            rules = [
                " REGLAS:",
                "",
                "- Explora el",
                "  mapa usando",
                "  las FLECHAS.",
                "",
                "- En batalla,",
                "  lanza el",
                "  dado para",
                "  ganar AP.",
                "",
                "- Usa AP para",
                "  jugar cartas.",
                "",
                "- Las cartas",
                "  escalan con",
                "  el dado.",
                "",
                "- Derrota al",
                "  enemigo en",
                "  40 seg.",
                "",
                "- Fin de",
                "  tiempo =",
                "  pierdes turno",
            ]
            y = 20
            for line in rules:
                if line.strip() == "REGLAS:":
                    text = self.font_small.render(line, True, (255, 200, 0))
                else:
                    text = self.font_small.render(line, True, (180, 170, 220))
                logical.blit(text, (894, y))
                y += 25

        # Draw level-up modal if there are pending level ups
        if hasattr(self.hero, 'pending_level_ups') and self.hero.pending_level_ups:
            current_lvl = self.hero.pending_level_ups[0]
            self._draw_level_up_modal(logical, current_lvl)

        scaled = pygame.transform.scale(logical, screen.get_size())
        screen.blit(scaled, (0, 0))

    def _draw_level_up_modal(self, surface, level):
        dim = pygame.Surface((1024, 640), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))  # Dark transparent overlay
        surface.blit(dim, (0, 0))
        
        # Modal Box
        modal_w, modal_h = 400, 260
        modal_x = (1024 - modal_w) // 2
        modal_y = (640 - modal_h) // 2
        
        # Background
        pygame.draw.rect(surface, (15, 10, 30), (modal_x, modal_y, modal_w, modal_h), border_radius=8)
        pygame.draw.rect(surface, (255, 215, 0), (modal_x, modal_y, modal_w, modal_h), 2, border_radius=8)
        
        # Title: ¡SUBISTE A NIVEL X!
        pulse = abs(math.sin(pygame.time.get_ticks() / 200.0))
        title_color = (255, 215 + int(40 * pulse), 100)
        title_text = self.font_large.render(f"¡SUBISTE A NIVEL {level}!", True, title_color)
        surface.blit(title_text, (512 - title_text.get_width() // 2, modal_y + 35))
        
        pygame.draw.line(surface, (100, 80, 160), (modal_x + 30, modal_y + 80), (modal_x + modal_w - 30, modal_y + 80), 1)
        
        # Stat changes:
        # +10 HP Máx
        # +5 Escudo Máx
        hp_text = self.font_medium.render("+10 HP Máx", True, (100, 255, 100))
        shield_text = self.font_medium.render("+5 Escudo Máx", True, (100, 255, 100))
        
        surface.blit(hp_text, (512 - hp_text.get_width() // 2, modal_y + 105))
        surface.blit(shield_text, (512 - shield_text.get_width() // 2, modal_y + 145))
        
        # Button: [ Aceptar ]
        btn_w, btn_h = 160, 40
        btn_x = 512 - btn_w // 2
        btn_y = modal_y + 195
        
        mx, my = pygame.mouse.get_pos()
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        is_hover = btn_rect.collidepoint((mx, my))
        
        btn_color = (60, 40, 120) if is_hover else (30, 20, 60)
        pygame.draw.rect(surface, btn_color, btn_rect, border_radius=6)
        pygame.draw.rect(surface, (255, 215, 0), btn_rect, 2, border_radius=6)
        
        btn_text = self.font_small.render("Aceptar", True, (255, 215, 0) if is_hover else (220, 220, 220))
        surface.blit(btn_text, (512 - btn_text.get_width() // 2, btn_y + (btn_h - btn_text.get_height()) // 2))

    def _get_color_rgb(self, color_name):
        for c in self.colors_available:
            if c["name"] == color_name:
                return c["rgb"]
        return (255, 255, 255)

    def _resolve_color_conflict(self):
        if not self.room_data or not self.game_client:
            return
        players = list(self.room_data.get("players", {}).values())
        other_players = [p for p in players if p.get("player_id") != self.player_id]
        
        current_color = self.hero.hero_color_name
        conflict = False
        for op in other_players:
            if op.get("hero_color") == current_color:
                if not self.is_host or (not self.is_host and op.get("is_host")):
                    conflict = True
                    break
                elif not self.is_host and not op.get("is_host") and self.player_id > op.get("player_id"):
                    conflict = True
                    break
        
        if conflict:
            occupied = [p.get("hero_color") for p in other_players]
            for c in self.colors_available:
                if c["name"] not in occupied:
                    self.hero.hero_color_name = c["name"]
                    self.hero.hero_color_rgb = c["rgb"]
                    self.auto_save()
                    sync_msg = {
                        "type": "SYNC_PLAYER",
                        "player": {
                            "player_id": self.player_id,
                            "player_name": self.hero.name,
                            "hero_color": self.hero.hero_color_name,
                            "hero_level": self.hero.level,
                            "hero_hp": self.hero.hp,
                            "hero_shield": self.hero.shield,
                            "position_x": 0.0,
                            "position_y": 0.0,
                            "is_host": self.is_host,
                            "hero_exp": self.hero.hero_exp
                        }
                    }
                    self.game_client.send_message(sync_msg)
                    print(f"[Game] Color conflict resolved: switched to {c['name']}")
                    break

    def _check_room_exists(self, code):
        import urllib.request
        import json
        from network.server_client import get_server_url, HAS_CLIENT
        
        if not HAS_CLIENT:
            return {"exists": True, "full": False}
            
        ws_url = get_server_url()
        if ws_url.startswith("wss://"):
            http_url = "https://" + ws_url[6:]
        elif ws_url.startswith("ws://"):
            http_url = "http://" + ws_url[5:]
        else:
            http_url = ws_url
            
        url = f"{http_url}/rooms/{code.upper()}"
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=3.0) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data
        except Exception as e:
            print(f"[Network] Error checking room: {e}")
            return {"error": str(e)}

    def _start_check_room(self, code):
        self.checking_room_thread = threading.Thread(target=self._thread_check_room, args=(code,), daemon=True)
        self.checking_room_result = None
        self.room_code = code.upper()
        self.menu_state = "CHECKING_ROOM"
        self.checking_room_thread.start()

    def _thread_check_room(self, code):
        res = self._check_room_exists(code)
        self.checking_room_result = res


if __name__ == "__main__":
    Game().run()
