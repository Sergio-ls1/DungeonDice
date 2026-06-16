"""
map.py  –  Visual RPG map with tiled terrain, camera, decorations and particles.

MECHANICS UNCHANGED:
  handle_event()    – returns None (encounter confirmation handled here visually)
  encounter_chance  – 0.08
  steps             – incremented on every move
  Enemy()           – spawned via pending_encounter flag read by game.py

Only draw() and its visual helpers changed.
"""

import pygame
import os
import random
import math
from pathlib import Path
from .entities import Enemy
from .sanctuary import SanctuaryMinigame, SANCTUARY_POSITIONS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE   = Path(__file__).resolve().parents[2]
FOREST = BASE / "tiny-RPG-forest-files" / "tiny-RPG-forest-files" / "Assets" / "PNG"

# ---------------------------------------------------------------------------
# World constants
# ---------------------------------------------------------------------------
TILE_SIZE = 32          # pixels per tile on screen
SRC_TILE  = 16          # source tile size inside tileset.png
MAP_W     = 50          # world width  in tiles
MAP_H     = 32          # world height in tiles
SCREEN_W  = 884         # game area width (excludes rules panel)
SCREEN_H  = 640         # game area height

# Terrain types
GRASS = 0
PATH  = 1
WATER = 2

# Extra margin in tiles when computing visible region – prevents edge gaps
DRAW_MARGIN = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _load_sheet(path, frame_w, frame_h, num_frames, scale=1):
    """Return list of pygame.Surface frames from a horizontal spritesheet."""
    frames = []
    res_path = resource_path(path)
    if not os.path.exists(res_path):
        return frames
    sheet = pygame.image.load(res_path).convert_alpha()
    sw, sh = sheet.get_size()
    actual = min(num_frames, sw // frame_w)
    for i in range(actual):
        r = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
        if r.right <= sw and r.bottom <= sh:
            frame = sheet.subsurface(r).copy()
            if scale != 1:
                w, h = frame.get_size()
                frame = pygame.transform.scale(frame, (int(w * scale), int(h * scale)))
            frames.append(frame)
    return frames


def _tint_sprite_surface(surf, target_color):
    if not surf or not target_color:
        return surf
    tinted = surf.copy()
    w, h = tinted.get_size()
    tr, tg, tb = target_color
    for x in range(w):
        for y in range(h):
            r, g, b, a = tinted.get_at((x, y))
            if a > 0:
                # Check if it's green-ish
                if g > r and g > b:
                    v = g / 255.0
                    nr = int(v * tr)
                    ng = int(v * tg)
                    nb = int(v * tb)
                    nr = max(0, min(255, nr))
                    ng = max(0, min(255, ng))
                    nb = max(0, min(255, nb))
                    tinted.set_at((x, y), (nr, ng, nb, a))
    return tinted


def _solid(color, w=TILE_SIZE, h=TILE_SIZE):
    s = pygame.Surface((w, h))
    s.fill(color)
    return s


# ---------------------------------------------------------------------------
# MapSystem
# ---------------------------------------------------------------------------
class MapSystem:

    # -----------------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------------
    def __init__(self, hero):
        self.hero              = hero
        self.steps             = 0
        self.pending_encounter = False
        self.encounter_chance  = 0.08   # MECHANIC – do not change

        # Encounter-panel state (visual gate before battle)
        self.show_encounter_panel  = False
        self._encounter_enemy_lvl  = 1   # level stored when encounter fires
        self._panel_anim           = 0.0  # for blinking prompt

        # Fonts
        font_path = BASE / "assets" / "fonts" / "pixel.ttf"
        res_font = resource_path(font_path)
        if os.path.exists(res_font):
            self.font_hp    = pygame.font.Font(res_font, 14)
            self.font_panel = pygame.font.Font(res_font, 16)
            self.font_enc   = pygame.font.Font(res_font, 22)
        else:
            self.font_hp    = pygame.font.SysFont("courier", 14, bold=True)
            self.font_panel = pygame.font.SysFont("courier", 16, bold=True)
            self.font_enc   = pygame.font.SysFont("courier", 22, bold=True)

        # Build world
        self._load_tiles()
        self._generate_map()
        self._bake_ground()

        # Decorations
        self._load_decorations()
        self._generate_decorations()

        # Hero animation on map
        self.map_hero_anims    = {"idle": [], "front": [], "side": [], "back": []}
        self._load_hero_animations()
        self.hero_anim_timer   = 0.0
        self.hero_frame_index  = 0
        self.hero_current_anim = "idle"
        self.hero_facing_right = True
        self.other_players_anims = {}

        # Enemy indicators (visual only)
        self._load_enemy_indicators()

        # Hero world position – centred on the map
        self.pos_x = float((MAP_W // 2) * TILE_SIZE + TILE_SIZE // 2)
        self.pos_y = float((MAP_H // 2) * TILE_SIZE + TILE_SIZE // 2)

        # Camera – start exactly on hero
        self.camera_x = self.pos_x - SCREEN_W / 2
        self.camera_y = self.pos_y - SCREEN_H / 2
        self._clamp_camera()

        # Ambient particles
        self.water_timer = 0.0
        self._init_particles()
        self.prev_keys = None
        self.colliding_enemy = None
        self.last_collided_type = None

        # ── Santuarios del Conocimiento ───────────────────────────────
        self._init_sanctuaries()
        self.show_sanctuary_panel = False
        self.active_sanctuary_idx = None
        self.sanctuary_minigame   = None
        self._sanctuary_panel_anim = 0.0

    # -----------------------------------------------------------------------
    # Tile loading
    # -----------------------------------------------------------------------
    def _load_tiles(self):
        tileset_path = FOREST / "environment" / "tileset.png"

        self.grass_tiles = []
        self.path_tiles  = []
        self.water_tiles = []
        self.path_tiles_dict = {}

        res_tileset = resource_path(tileset_path)
        if not os.path.exists(res_tileset):
            self._fallback_tiles()
            return

        tileset = pygame.image.load(res_tileset).convert_alpha()
        tw, th  = tileset.get_size()   # 544 × 512, 16-px grid

        def ext(col, row, sz=SRC_TILE):
            px, py = col * sz, row * sz
            r = pygame.Rect(px, py, sz, sz)
            if r.right <= tw and r.bottom <= th:
                return pygame.transform.scale(
                    tileset.subsurface(r).copy(), (TILE_SIZE, TILE_SIZE))
            return None

        # Grass – pure grass tiles in tileset
        for pos in [(18, 9), (21, 9), (23, 9), (25, 9), (28, 9),
                    (0, 10), (1, 10), (5, 10), (10, 10)]:
            t = ext(*pos)
            if t:
                self.grass_tiles.append(t)

        # Path – brownish tiles (cols 2-4, rows 1-3)
        for col in [2, 3, 4]:
            for row in [1, 2, 3]:
                t = ext(col, row)
                if t:
                    self.path_tiles_dict[(col, row)] = t
                    self.path_tiles.append(t)

        # Water – procedural
        for i, shade in enumerate([(28,65,130),(32,72,142),(24,58,118),(30,68,135)]):
            ws = pygame.Surface((TILE_SIZE, TILE_SIZE))
            ws.fill(shade)
            for wy in range(0, TILE_SIZE, 5):
                off = (i * 4 + wy) % 6
                wc  = (shade[0]+15, shade[1]+22, min(255, shade[2]+30))
                pygame.draw.line(ws, wc, (off, wy), (TILE_SIZE, wy), 1)
            self.water_tiles.append(ws)

        if not self.grass_tiles:
            self._fallback_tiles()
            return
        if not self.path_tiles:
            for base in self.grass_tiles[:3]:
                p = base.copy()
                t = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                t.fill((80, 45, 10, 120))
                p.blit(t, (0, 0))
                self.path_tiles.append(p)
                for col in [2, 3, 4]:
                    for row in [1, 2, 3]:
                        self.path_tiles_dict[(col, row)] = p

        # Keep a reference grass colour for filling screen edges
        self._grass_fill_color = (42, 88, 28)

    def _fallback_tiles(self):
        self.path_tiles_dict = {}
        for c in [(42,90,28),(48,96,32),(38,84,24),(44,92,30),(50,98,34)]:
            self.grass_tiles.append(_solid(c))
        c_list = [(130,98,55),(122,90,48),(138,105,60)]
        for c in c_list:
            self.path_tiles.append(_solid(c))
        # Populate path_tiles_dict
        for col in [2, 3, 4]:
            for row in [1, 2, 3]:
                c = c_list[(col + row) % len(c_list)]
                self.path_tiles_dict[(col, row)] = _solid(c)
        for c in [(28,65,130),(32,72,142)]:
            self.water_tiles.append(_solid(c))
        self._grass_fill_color = (42, 88, 28)

    # -----------------------------------------------------------------------
    # Map generation
    # -----------------------------------------------------------------------
    def _generate_map(self):
        rng = random.Random(42)
        self.tiles        = [[GRASS]*MAP_W for _ in range(MAP_H)]
        self.tile_variant = [[0]*MAP_W     for _ in range(MAP_H)]

        # Water border (constant, uniform thickness of 3 tiles around the map edges)
        border_thickness = 3
        for y in range(MAP_H):
            for x in range(MAP_W):
                if x < border_thickness or x >= MAP_W - border_thickness or \
                   y < border_thickness or y >= MAP_H - border_thickness:
                    self.tiles[y][x] = WATER

        # Paths
        self._carve_path([(4,16),(10,13),(16,17),(22,14),(28,16),(34,13),(40,17),(46,15)], 1.6)
        self._carve_path([(25,4),(23,9),(25,15),(27,21),(25,28)], 1.4)
        self._carve_path([(10,13),(8,8),(12,5)], 1.2)
        self._carve_path([(34,13),(37,8),(40,5)], 1.2)

        # Ponds
        for px, py, r in [(10,7,2.2),(38,24,1.9),(42,7,1.6),(18,25,1.5)]:
            for y in range(MAP_H):
                for x in range(MAP_W):
                    d  = math.sqrt((x-px)**2+(y-py)**2)
                    pn = math.sin(x*1.5+y*0.9)*0.3
                    if d < r+pn and self.tiles[y][x] != PATH:
                        self.tiles[y][x] = WATER

        # Variants
        for y in range(MAP_H):
            for x in range(MAP_W):
                tt = self.tiles[y][x]
                if   tt == GRASS: self.tile_variant[y][x] = rng.randint(0, len(self.grass_tiles)-1)
                elif tt == PATH:  self.tile_variant[y][x] = rng.randint(0, len(self.path_tiles)-1)
                else:             self.tile_variant[y][x] = rng.randint(0, len(self.water_tiles)-1)

    def _carve_path(self, pts, width=1.5):
        for seg in range(len(pts)-1):
            x0,y0 = pts[seg]; x1,y1 = pts[seg+1]
            dist  = math.sqrt((x1-x0)**2+(y1-y0)**2)
            steps = int(dist*3)+1
            for t in range(steps+1):
                frac = t/max(1,steps)
                px   = x0+(x1-x0)*frac
                py   = y0+(y1-y0)*frac
                for dy in range(-2,3):
                    for dx in range(-2,3):
                        ix,iy = int(round(px+dx)), int(round(py+dy))
                        if 0<=ix<MAP_W and 0<=iy<MAP_H:
                            if math.sqrt(dx*dx+dy*dy)<=width and self.tiles[iy][ix]!=WATER:
                                self.tiles[iy][ix] = PATH

    # -----------------------------------------------------------------------
    # Pre-bake ground surface
    # -----------------------------------------------------------------------
    def _get_path_tile(self, x, y):
        # Auto-tiling connection check
        def is_path(nx, ny):
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                return self.tiles[ny][nx] == PATH
            return False

        up = is_path(x, y - 1)
        down = is_path(x, y + 1)
        left = is_path(x - 1, y)
        right = is_path(x + 1, y)

        # Default center tile of path
        col, row = 3, 2

        # 9-slice mapping
        if not up and not left:
            col, row = 2, 1  # Top-Left corner
        elif not up and not right:
            col, row = 4, 1  # Top-Right corner
        elif not down and not left:
            col, row = 2, 3  # Bottom-Left corner
        elif not down and not right:
            col, row = 4, 3  # Bottom-Right corner
        elif not up:
            col, row = 3, 1  # Top edge
        elif not down:
            col, row = 3, 3  # Bottom edge
        elif not left:
            col, row = 2, 2  # Left edge
        elif not right:
            col, row = 4, 2  # Right edge

        # Get tile from dict, fallback to loaded list
        return self.path_tiles_dict.get((col, row), self.path_tiles[0] if self.path_tiles else None)

    # -----------------------------------------------------------------------
    # Pre-bake ground surface
    # -----------------------------------------------------------------------
    def _bake_ground(self):
        # Fill with grass colour so any unblitted pixel matches terrain
        self.ground_surface = pygame.Surface((MAP_W*TILE_SIZE, MAP_H*TILE_SIZE))
        self.ground_surface.fill(self._grass_fill_color)

        for y in range(MAP_H):
            for x in range(MAP_W):
                tt = self.tiles[y][x]
                vi = self.tile_variant[y][x]
                if   tt == GRASS: tile = self.grass_tiles[vi % len(self.grass_tiles)]
                elif tt == PATH:  tile = self._get_path_tile(x, y)
                else:             tile = self.water_tiles[vi % len(self.water_tiles)]
                self.ground_surface.blit(tile, (x*TILE_SIZE, y*TILE_SIZE))

        # Edge blending
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] == WATER:
                    continue
                for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx,ny = x+dx, y+dy
                    if 0<=nx<MAP_W and 0<=ny<MAP_H and self.tiles[ny][nx]==WATER:
                        e = pygame.Surface((TILE_SIZE,TILE_SIZE), pygame.SRCALPHA)
                        e.fill((0,12,30,60))
                        self.ground_surface.blit(e, (x*TILE_SIZE, y*TILE_SIZE))
                        break

        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] != PATH:
                    continue
                for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx,ny = x+dx, y+dy
                    if 0<=nx<MAP_W and 0<=ny<MAP_H and self.tiles[ny][nx]==GRASS:
                        e = pygame.Surface((TILE_SIZE,TILE_SIZE), pygame.SRCALPHA)
                        e.fill((25,45,5,28))
                        self.ground_surface.blit(e, (x*TILE_SIZE, y*TILE_SIZE))
                        break

    # -----------------------------------------------------------------------
    # Decorations
    # -----------------------------------------------------------------------
    def _load_decorations(self):
        sliced = FOREST / "environment" / "sliced-objects"
        self.dec_imgs = {}
        defs = {
            "tree_orange": (sliced/"tree-orange.png",   2.2),
            "tree_pink":   (sliced/"tree-pink.png",     2.2),
            "tree_dried":  (sliced/"tree-dried.png",    2.0),
            "rock":        (sliced/"rock.png",          1.6),
            "rock_big":    (sliced/"rock-monument.png", 1.3),
            "bush":        (sliced/"bush.png",          1.6),
            "bush_tall":   (sliced/"bush-tall.png",     1.6),
            "sign":        (sliced/"sign.png",          1.8),
            "trunk":       (sliced/"trunk.png",         1.6),
        }
        for key, (p, scale) in defs.items():
            res_p = resource_path(p)
            if os.path.exists(res_p):
                img = pygame.image.load(res_p).convert_alpha()
                w,h = img.get_size()
                self.dec_imgs[key] = pygame.transform.scale(img,(int(w*scale),int(h*scale)))

    def _generate_decorations(self):
        rng = random.Random(123)
        self.decorations = []

        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] != GRASS:
                    continue
                # Never spawn decorations near the starting position (25, 16)
                if abs(x - 25) <= 2 and abs(y - 16) <= 2:
                    continue
                # Never spawn decorations within 1 tile of any sanctuary
                near_sanc = False
                for sx, sy in SANCTUARY_POSITIONS:
                    if abs(x - sx) <= 1 and abs(y - sy) <= 1:
                        near_sanc = True
                        break
                if near_sanc:
                    continue
                pd = self._dist_to_type(x, y, PATH)
                r  = rng.random()
                if pd > 3:
                    if r < 0.06:
                        key = rng.choice(["tree_orange","tree_pink"])
                        if key in self.dec_imgs:
                            ox,oy = rng.randint(-5,5), rng.randint(-5,5)
                            self.decorations.append((key,
                                x*TILE_SIZE+TILE_SIZE//2+ox,
                                y*TILE_SIZE+TILE_SIZE//2+oy))
                    elif r < 0.08:
                        key = "tree_dried" if rng.random()<0.3 else rng.choice(["tree_orange","tree_pink"])
                        if key in self.dec_imgs:
                            self.decorations.append((key,
                                x*TILE_SIZE+TILE_SIZE//2,
                                y*TILE_SIZE+TILE_SIZE//2))
                elif pd >= 1:
                    if r < 0.04:
                        key = rng.choice(["rock","bush","bush_tall"])
                        if key in self.dec_imgs:
                            self.decorations.append((key,
                                x*TILE_SIZE+TILE_SIZE//2,
                                y*TILE_SIZE+TILE_SIZE//2))
                    elif r < 0.06:
                        key = rng.choice(["tree_orange","tree_pink"])
                        if key in self.dec_imgs:
                            self.decorations.append((key,
                                x*TILE_SIZE+TILE_SIZE//2,
                                y*TILE_SIZE+TILE_SIZE//2))

        if "sign"     in self.dec_imgs: self.decorations.append(("sign",    26*TILE_SIZE,    13*TILE_SIZE))
        if "trunk"    in self.dec_imgs:
            for tx,ty in [(14,16),(30,14),(22,9)]:
                self.decorations.append(("trunk", tx*TILE_SIZE+16, ty*TILE_SIZE+16))
        if "rock_big" in self.dec_imgs:
            for wx,wy in [(9,9),(39,25),(43,9)]:
                self.decorations.append(("rock_big", wx*TILE_SIZE+8, wy*TILE_SIZE+8))

        self.decorations.sort(key=lambda d: d[2])

    def _dist_to_type(self, x, y, tile_type):
        best = 999.0
        for r in range(1, 8):
            for dx in range(-r, r+1):
                for dy in range(-r, r+1):
                    nx,ny = x+dx, y+dy
                    if 0<=nx<MAP_W and 0<=ny<MAP_H and self.tiles[ny][nx]==tile_type:
                        d = math.sqrt(dx*dx+dy*dy)
                        if d < best: best = d
            if best < r: break
        return best

    def collides_with_decorations(self, x, y):
        # Hero feet bounding box in world coordinates
        # Center of sprite is at x, bottom of sprite is y + 32.
        # We define a small box near feet.
        hero_rect = pygame.Rect(int(x - 8), int(y + 16), 16, 12)
        
        for key, wx, wy in self.decorations:
            # Determine collision box for this decoration based on type
            if key in ["tree_orange", "tree_pink"]:
                dec_rect = pygame.Rect(wx - 14, wy - 16, 28, 16)
            elif key == "tree_dried":
                dec_rect = pygame.Rect(wx - 18, wy - 20, 36, 20)
            elif key == "rock":
                dec_rect = pygame.Rect(wx - 20, wy - 16, 40, 16)
            elif key == "rock_big":
                dec_rect = pygame.Rect(wx - 48, wy - 28, 96, 28)
            elif key == "bush":
                dec_rect = pygame.Rect(wx - 18, wy - 14, 36, 14)
            elif key == "bush_tall":
                dec_rect = pygame.Rect(wx - 10, wy - 14, 20, 14)
            elif key == "sign":
                dec_rect = pygame.Rect(wx - 10, wy - 12, 20, 12)
            elif key == "trunk":
                dec_rect = pygame.Rect(wx - 22, wy - 16, 44, 16)
            else:
                continue
                
            if hero_rect.colliderect(dec_rect):
                return True
        return False

    # -----------------------------------------------------------------------
    # Particles
    # -----------------------------------------------------------------------
    def _init_particles(self):
        rng = random.Random(77)
        self.leaf_particles = []
        for _ in range(40):
            self.leaf_particles.append({
                "x":     rng.uniform(0, MAP_W*TILE_SIZE),
                "y":     rng.uniform(0, MAP_H*TILE_SIZE),
                "vx":    rng.uniform(-14, -5),
                "vy":    rng.uniform(6, 18),
                "color": rng.choice([(185,85,40),(165,58,28),(205,145,52),(145,48,22),(195,105,48)]),
                "size":  rng.randint(2, 4),
                "phase": rng.uniform(0, 6.28),
            })

    def _update_particles(self, dt):
        for p in self.leaf_particles:
            p["x"] += p["vx"]*dt + math.sin(p["phase"]+self.water_timer*1.5)*8*dt
            p["y"] += p["vy"]*dt
            if p["y"] > MAP_H*TILE_SIZE or p["x"] < 0:
                p["y"] = random.uniform(-20, 0)
                p["x"] = random.uniform(0, MAP_W*TILE_SIZE)

    # -----------------------------------------------------------------------
    # Hero & enemy sprites
    # -----------------------------------------------------------------------
    def _load_hero_animations(self):
        hero_dir = FOREST / "spritesheets" / "hero"
        color = getattr(self.hero, "hero_color_rgb", (220, 60, 60))
        self.map_hero_anims["idle"]  = [_tint_sprite_surface(f, color) for f in _load_sheet(hero_dir/"idle"/"hero-idle-front.png", 32,32,1, scale=2)]
        self.map_hero_anims["front"] = [_tint_sprite_surface(f, color) for f in _load_sheet(hero_dir/"walk"/"hero-walk-front.png", 32,32,6, scale=2)]
        self.map_hero_anims["side"]  = [_tint_sprite_surface(f, color) for f in _load_sheet(hero_dir/"walk"/"hero-walk-side.png",  32,32,6, scale=2)]
        self.map_hero_anims["back"]  = [_tint_sprite_surface(f, color) for f in _load_sheet(hero_dir/"walk"/"hero-back-walk.png",  32,32,6, scale=2)]

    def _load_enemy_indicators(self):
        ss = FOREST / "spritesheets"
        self.mole_frames   = _load_sheet(ss/"mole"/"walk"/"mole-walk-front.png",     24,24,4, scale=2)
        if not self.mole_frames:
            self.mole_frames = _load_sheet(ss/"mole"/"idle"/"mole-idle-front.png",   24,24,1, scale=2)
        self.treant_frames = _load_sheet(ss/"treant"/"walk"/"treant-walk-front.png", 31,35,4, scale=2)
        if not self.treant_frames:
            self.treant_frames = _load_sheet(ss/"treant"/"idle"/"treant-idle-front.png",31,35,1, scale=2)
        self.enemy_anim_timer = 0.0
        self.mole_positions   = [
            (10*TILE_SIZE, 13*TILE_SIZE+TILE_SIZE//2),
            (22*TILE_SIZE, 14*TILE_SIZE+TILE_SIZE//2),
            (28*TILE_SIZE, 16*TILE_SIZE+TILE_SIZE//2),
            (40*TILE_SIZE, 17*TILE_SIZE+TILE_SIZE//2),
        ]
        self.treant_positions = [
            (16*TILE_SIZE, 17*TILE_SIZE+TILE_SIZE//2),
            (34*TILE_SIZE, 13*TILE_SIZE+TILE_SIZE//2),
            ( 8*TILE_SIZE,  8*TILE_SIZE+TILE_SIZE//2),
        ]

    # -----------------------------------------------------------------------
    # Sanctuaries
    # -----------------------------------------------------------------------
    def _init_sanctuaries(self):
        """Create sanctuary data list, respecting already-completed sanctuaries."""
        completed = set(self.hero.completed_sanctuaries)
        self.sanctuaries = []
        for idx, (tx, ty) in enumerate(SANCTUARY_POSITIONS):
            # Ensure position is on a grass tile and within bounds
            tx = max(0, min(tx, MAP_W - 1))
            ty = max(0, min(ty, MAP_H - 1))
            # Force tile to grass if it ended up as water
            if self.tiles[ty][tx] == WATER:
                ty = max(3, ty - 1)
            self.sanctuaries.append({
                "idx":       idx,
                "wx":        tx * TILE_SIZE + TILE_SIZE // 2,
                "wy":        ty * TILE_SIZE + TILE_SIZE // 2,
                "completed": idx in completed,
            })
        self._sanctuary_glow_timer = 0.0

    def _draw_sanctuary_panel(self, screen):
        """Approach panel: Santuario del Conocimiento / [ENTER] Ingresar / [ESC] Continuar"""
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 130))
        screen.blit(dim, (0, 0))

        pw, ph = 480, 210
        px = (SCREEN_W - pw) // 2
        py = (SCREEN_H - ph) // 2

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for row in range(ph):
            alpha = 230 - int(row / ph * 20)
            pygame.draw.line(panel, (8, 10, 35, alpha), (0, row), (pw, row))
        screen.blit(panel, (px, py))

        border_col = (100, 160, 255)
        pygame.draw.rect(screen, border_col, (px, py, pw, ph), 2)
        clen = 14
        for cx, cy, ddx, ddy in [
            (px, py, 1, 1), (px+pw-1, py, -1, 1),
            (px, py+ph-1, 1, -1), (px+pw-1, py+ph-1, -1, -1),
        ]:
            pygame.draw.line(screen, (255, 215, 0), (cx, cy), (cx+ddx*clen, cy), 2)
            pygame.draw.line(screen, (255, 215, 0), (cx, cy), (cx, cy+ddy*clen), 2)

        t1 = self.font_enc.render("Santuario del Conocimiento", True, (130, 200, 255))
        screen.blit(t1, t1.get_rect(center=(px + pw // 2, py + 38)))

        pygame.draw.line(screen, (70, 110, 200), (px+30, py+60), (px+pw-30, py+60), 1)

        t_enter = self.font_panel.render("[ENTER]  Ingresar al Santuario", True, (140, 255, 180))
        t_esc   = self.font_panel.render("[ESC]    Continuar", True, (200, 180, 180))
        screen.blit(t_enter, t_enter.get_rect(center=(px + pw // 2, py + 100)))
        screen.blit(t_esc,   t_esc.get_rect(center=(px + pw // 2, py + 138)))

        pygame.draw.line(screen, (70, 110, 200), (px+30, py+162), (px+pw-30, py+162), 1)

        blink_a = int((math.sin(self._sanctuary_panel_anim * 4) + 1) / 2 * 255)
        prompt = self.font_hp.render("Selecciona una opción", True, (160, 160, 200))
        ps = pygame.Surface(prompt.get_size(), pygame.SRCALPHA)
        ps.fill((255, 255, 255, blink_a))
        prompt.blit(ps, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(prompt, prompt.get_rect(center=(px + pw // 2, py + 186)))

    # -----------------------------------------------------------------------
    # handle_event – PRESERVED (encounter confirmation uses update/draw only)
    # -----------------------------------------------------------------------
    def handle_event(self, event):
        # Forward events to active minigame
        if self.sanctuary_minigame is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.sanctuary_minigame.handle_mouse(event.pos)
            else:
                self.sanctuary_minigame.handle_event(event)
        return None

    # -----------------------------------------------------------------------
    # Camera
    # -----------------------------------------------------------------------
    def _clamp_camera(self):
        max_cx = float(MAP_W*TILE_SIZE - SCREEN_W)
        max_cy = float(MAP_H*TILE_SIZE - SCREEN_H)
        self.camera_x = max(0.0, min(float(self.camera_x), max_cx))
        self.camera_y = max(0.0, min(float(self.camera_y), max_cy))

    def _update_camera(self):
        target_x = self.pos_x - SCREEN_W/2
        target_y = self.pos_y - SCREEN_H/2
        max_cx   = float(MAP_W*TILE_SIZE - SCREEN_W)
        max_cy   = float(MAP_H*TILE_SIZE - SCREEN_H)
        target_x = max(0.0, min(target_x, max_cx))
        target_y = max(0.0, min(target_y, max_cy))
        lerp = 0.10
        self.camera_x += (target_x - self.camera_x)*lerp
        self.camera_y += (target_y - self.camera_y)*lerp
        self.camera_x = max(0.0, min(self.camera_x, max_cx))
        self.camera_y = max(0.0, min(self.camera_y, max_cy))

    # -----------------------------------------------------------------------
    # update() – MECHANICS PRESERVED
    # -----------------------------------------------------------------------
    def update(self):
        keys = pygame.key.get_pressed()
        if self.prev_keys is None:
            self.prev_keys = keys

        # While encounter panel is visible, freeze movement but animate panel
        # ── Santuario minijuego activo ────────────────────────────────
        if self.sanctuary_minigame is not None:
            dt = 1 / 60.0
            self.sanctuary_minigame.update(dt)
            self.water_timer += dt
            self._update_particles(dt)
            self.enemy_anim_timer += dt
            self._sanctuary_panel_anim += dt
            if self.sanctuary_minigame.done:
                # Mark sanctuary completed in hero
                idx = self.active_sanctuary_idx
                if idx is not None:
                    if self.sanctuary_minigame.correct_count == self.sanctuary_minigame.QUESTIONS_PER_SESSION:
                        self.sanctuaries[idx]["completed"] = True
                        if idx not in self.hero.completed_sanctuaries:
                            self.hero.completed_sanctuaries.append(idx)
                            self.hero.add_exp(15)
                self.sanctuary_minigame   = None
                self.prev_keys = keys
            return

        # ── Panel de santuario (acercarse) ──────────────────────────────
        if self.show_sanctuary_panel:
            self._sanctuary_panel_anim += 1 / 60.0
            self.water_timer  += 1 / 60.0
            self._update_particles(1 / 60.0)
            self.enemy_anim_timer += 1 / 60.0

            enter_pressed = (
                (keys[pygame.K_RETURN] or keys[pygame.K_KP_ENTER]) and
                not (self.prev_keys[pygame.K_RETURN] or self.prev_keys[pygame.K_KP_ENTER])
            )
            esc_pressed = keys[pygame.K_ESCAPE] and not self.prev_keys[pygame.K_ESCAPE]

            if enter_pressed:
                self.show_sanctuary_panel = False
                # Open minigame
                self.sanctuary_minigame = SanctuaryMinigame(self.hero)
                self._sanctuary_panel_anim = 0.0
            elif esc_pressed:
                self.show_sanctuary_panel = False

            self.prev_keys = keys
            return

        if self.show_encounter_panel:
            self._panel_anim += 1/60.0
            self.water_timer  += 1/60.0
            self._update_particles(1/60.0)
            self.enemy_anim_timer += 1/60.0
            
            # Detect key down events (edge trigger)
            enter_pressed = (keys[pygame.K_RETURN] or keys[pygame.K_KP_ENTER]) and not (self.prev_keys[pygame.K_RETURN] or self.prev_keys[pygame.K_KP_ENTER])
            esc_pressed = keys[pygame.K_ESCAPE] and not self.prev_keys[pygame.K_ESCAPE]
            
            if enter_pressed:
                # Confirm – let game.py pick up pending_encounter
                self.show_encounter_panel = False
                self.pending_encounter    = True
                
                # Remove the enemy from the map lists
                if self.colliding_enemy:
                    if self.colliding_enemy in self.mole_positions:
                        self.mole_positions.remove(self.colliding_enemy)
                    elif self.colliding_enemy in self.treant_positions:
                        self.treant_positions.remove(self.colliding_enemy)
                    self.colliding_enemy = None
            elif esc_pressed:
                # Cancel this encounter only
                self.show_encounter_panel = False
                
            self.prev_keys = keys
            return

        dx = dy = 0
        speed = 3
        if keys[pygame.K_LEFT]:  dx = -speed
        if keys[pygame.K_RIGHT]: dx =  speed
        if keys[pygame.K_UP]:    dy = -speed
        if keys[pygame.K_DOWN]:  dy =  speed

        moved = dx != 0 or dy != 0
        if moved:
            old_x, old_y = self.pos_x, self.pos_y
            
            # Try horizontal movement
            if dx != 0:
                new_x = max(TILE_SIZE/2, min(self.pos_x + dx, MAP_W*TILE_SIZE-TILE_SIZE/2))
                tx = int(new_x // TILE_SIZE)
                ty = int(self.pos_y // TILE_SIZE)
                if self.tiles[ty][tx] != WATER and not self.collides_with_decorations(new_x, self.pos_y):
                    self.pos_x = new_x
            
            # Try vertical movement
            if dy != 0:
                new_y = max(TILE_SIZE/2, min(self.pos_y + dy, MAP_H*TILE_SIZE-TILE_SIZE/2))
                tx = int(self.pos_x // TILE_SIZE)
                ty = int(new_y // TILE_SIZE)
                if self.tiles[ty][tx] != WATER and not self.collides_with_decorations(self.pos_x, new_y):
                    self.pos_y = new_y
                    
            if self.pos_x != old_x or self.pos_y != old_y:
                self.steps += 1                          # MECHANIC preserved

        # ── Check sanctuary proximity ────────────────────────────────
        self._sanctuary_glow_timer += 1 / 60.0
        near_sanctuary = False
        for s in self.sanctuaries:
            if s["completed"]:
                continue
            dist = math.sqrt((self.pos_x - s["wx"])**2 + (self.pos_y - s["wy"])**2)
            if dist < 48:
                near_sanctuary = True
                if not self.show_sanctuary_panel and self.active_sanctuary_idx != s["idx"]:
                    self.active_sanctuary_idx  = s["idx"]
                    self.show_sanctuary_panel  = True
                    self._sanctuary_panel_anim = 0.0
                    self.prev_keys = keys   # edge-trigger guard
                break
        if not near_sanctuary:
            self.show_sanctuary_panel = False
            self.active_sanctuary_idx = None

        # Check for collisions with visible enemies (Mole or Treant)
        active_collision = None
        collided_type = None
        for pos in self.mole_positions:
            dist = math.sqrt((self.pos_x - pos[0])**2 + (self.pos_y - pos[1])**2)
            if dist < 24:
                active_collision = pos
                collided_type = "mole"
                break
        if not active_collision:
            for pos in self.treant_positions:
                dist = math.sqrt((self.pos_x - pos[0])**2 + (self.pos_y - pos[1])**2)
                if dist < 24:
                    active_collision = pos
                    collided_type = "treant"
                    break

        if active_collision:
            if self.colliding_enemy != active_collision:
                self.colliding_enemy = active_collision
                self.last_collided_type = collided_type
                self.show_encounter_panel = True
                self._encounter_enemy_lvl = self.hero.level
                self._panel_anim          = 0.0
                self.prev_keys            = keys  # Ignore current keys on panel open
        else:
            self.colliding_enemy = None

        # Animation (visual only)
        if moved:
            if   dx > 0: self.hero_facing_right = True;  self.hero_current_anim = "side"
            elif dx < 0: self.hero_facing_right = False; self.hero_current_anim = "side"
            elif dy > 0: self.hero_current_anim = "front"
            elif dy < 0: self.hero_current_anim = "back"
        else:
            self.hero_current_anim = "idle"

        self.hero_anim_timer += 1/60.0
        if self.hero_anim_timer >= 0.10:
            self.hero_anim_timer  = 0.0
            self.hero_frame_index += 1
            frames = self.map_hero_anims.get(self.hero_current_anim, [])
            if frames:
                self.hero_frame_index %= len(frames)

        self._update_camera()
        self.enemy_anim_timer += 1/60.0
        self.water_timer      += 1/60.0
        self._update_particles(1/60.0)
        
        self.prev_keys = keys

    # -----------------------------------------------------------------------
    # Drawing helpers
    # -----------------------------------------------------------------------
    def _get_hero_frame(self):
        frames = self.map_hero_anims.get(self.hero_current_anim, [])
        if not frames:
            return None
        frame = frames[self.hero_frame_index % len(frames)]
        if self.hero_current_anim == "side" and not self.hero_facing_right:
            frame = pygame.transform.flip(frame, True, False)
        return frame

    def _draw_enemy_indicator(self, screen, frames, world_pos, cam_x, cam_y):
        if not frames:
            return
        wx, wy = world_pos
        sx = int(wx - cam_x)
        sy = int(wy - cam_y)
        if -64 < sx < SCREEN_W+64 and -64 < sy < SCREEN_H+64:
            idx   = int(self.enemy_anim_timer * 5) % len(frames)
            frame = frames[idx]
            rect  = frame.get_rect(center=(sx, sy))
            screen.blit(frame, rect)

    # -----------------------------------------------------------------------
    # Encounter confirmation panel (visual only – no mechanic changes)
    # -----------------------------------------------------------------------
    def _draw_encounter_panel(self, screen):
        # Dim the whole screen
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        screen.blit(dim, (0, 0))

        # Panel geometry
        pw, ph = 480, 220
        px = (SCREEN_W - pw) // 2
        py = (SCREEN_H - ph) // 2

        # Panel background (layered gradient)
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for row in range(ph):
            alpha = 230 - int(row / ph * 30)
            pygame.draw.line(panel, (12, 8, 28, alpha), (0, row), (pw, row))
        screen.blit(panel, (px, py))

        # Border + corner accents
        border_col = (180, 140, 50)
        pygame.draw.rect(screen, border_col, (px, py, pw, ph), 2)
        clen = 14
        for cx, cy, ddx, ddy in [
            (px, py, 1, 1), (px+pw-1, py, -1, 1),
            (px, py+ph-1, 1, -1), (px+pw-1, py+ph-1, -1, -1),
        ]:
            pygame.draw.line(screen, (255, 215, 0), (cx, cy), (cx+ddx*clen, cy), 2)
            pygame.draw.line(screen, (255, 215, 0), (cx, cy), (cx, cy+ddy*clen), 2)

        # Title
        t1 = self.font_enc.render("¡Has encontrado un enemigo!", True, (255, 200, 60))
        screen.blit(t1, t1.get_rect(center=(px+pw//2, py+38)))

        # Divider
        pygame.draw.line(screen, (120, 95, 40), (px+30, py+62), (px+pw-30, py+62), 1)

        # Options
        enter_str = "[ENTER] Enfrentar"
        esc_str   = "[ESC] Cancelar"

        t_enter = self.font_panel.render(enter_str, True, (140, 255, 140))
        t_esc   = self.font_panel.render(esc_str,   True, (200, 180, 180))
        screen.blit(t_enter, t_enter.get_rect(center=(px+pw//2, py+100)))
        screen.blit(t_esc,   t_esc.get_rect(center=(px+pw//2, py+138)))

        # Divider
        pygame.draw.line(screen, (120, 95, 40), (px+30, py+160), (px+pw-30, py+160), 1)

        # Blinking prompt
        blink_alpha = int((math.sin(self._panel_anim * 4) + 1) / 2 * 255)
        prompt = self.font_hp.render("Selecciona una opción", True, (160, 160, 200))
        ps = pygame.Surface(prompt.get_size(), pygame.SRCALPHA)
        ps.fill((255, 255, 255, blink_alpha))
        prompt.blit(ps, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(prompt, prompt.get_rect(center=(px+pw//2, py+188)))

    # -----------------------------------------------------------------------
    # draw() – full 6-layer rendering with gap-free ground
    # -----------------------------------------------------------------------
    def draw(self, screen, font, room_data=None, local_player_id=""):
        # Integer camera offsets for crisp rendering
        camera_x = self.camera_x
        camera_y = self.camera_y

        tile_x = int(camera_x // TILE_SIZE)
        tile_y = int(camera_y // TILE_SIZE)

        offset_x = int(camera_x % TILE_SIZE)
        offset_y = int(camera_y % TILE_SIZE)

        # ── Fill screen with grass colour first ───────────────────────────
        screen.fill(self._grass_fill_color)

        # ── Layer 1: Ground (tile-by-tile with margins and out-of-bounds fallbacks) ──
        margin = DRAW_MARGIN  # which is 2
        start_col = tile_x - margin
        start_row = tile_y - margin
        
        cols_to_render = math.ceil(SCREEN_W / TILE_SIZE) + 2 * margin + 1
        rows_to_render = math.ceil(SCREEN_H / TILE_SIZE) + 2 * margin + 1

        for i in range(rows_to_render):
            row = start_row + i
            for j in range(cols_to_render):
                col = start_col + j
                
                screen_x = (col - tile_x) * TILE_SIZE - offset_x
                screen_y = (row - tile_y) * TILE_SIZE - offset_y
                
                if 0 <= col < MAP_W and 0 <= row < MAP_H:
                    # Blit from pre-baked ground surface to retain blending
                    screen.blit(
                        self.ground_surface,
                        (screen_x, screen_y),
                        area=pygame.Rect(col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                    )
                else:
                    # Fallback tile for out of bounds: use a deterministic water tile
                    vi = (col * 7 + row * 13) % len(self.water_tiles)
                    tile = self.water_tiles[vi]
                    screen.blit(tile, (screen_x, screen_y))

        # ── Layer 2: Animated water shimmer ───────────────────────────────
        shimmer = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        for i in range(rows_to_render):
            row = start_row + i
            for j in range(cols_to_render):
                col = start_col + j
                is_out_of_bounds = not (0 <= col < MAP_W and 0 <= row < MAP_H)
                if is_out_of_bounds or self.tiles[row][col] == WATER:
                    a = int(20 + 15 * math.sin(
                        self.water_timer*2.5 + col*0.6 + row*0.4))
                    shimmer.fill((90, 155, 255, max(0, min(255, a))))
                    screen_x = (col - tile_x) * TILE_SIZE - offset_x
                    screen_y = (row - tile_y) * TILE_SIZE - offset_y
                    screen.blit(shimmer, (screen_x, screen_y))

        # ── Layers 3, 4, 5: Depth-Sorted (Y-sorted) Ground Elements ────────
        render_queue = []
        cam_x = int(camera_x)
        cam_y = int(camera_y)

        # 0. Collect Sanctuaries
        glow_t = self._sanctuary_glow_timer
        for s in self.sanctuaries:
            sx_w = int(s["wx"] - cam_x)
            sy_w = int(s["wy"] - cam_y)
            if -64 < sx_w < SCREEN_W + 64 and -64 < sy_w < SCREEN_H + 64:
                render_queue.append((s["wy"] + 4, "sanctuary", s, sx_w, sy_w, glow_t))

        # 1. Collect Decorations
        for key, wx, wy in self.decorations:
            img = self.dec_imgs.get(key)
            if img is not None:
                iw, ih = img.get_size()
                sx = int(wx - cam_x)
                sy = int(wy - cam_y)
                # Cull checks
                if not (sx+iw < -64 or sx > SCREEN_W+64 or sy+ih < -96 or sy > SCREEN_H+64):
                    render_queue.append((wy, "dec", img, sx - iw//2, sy - ih))

        # 2. Collect Enemy indicators (Mole)
        for pos in self.mole_positions:
            if self.mole_frames:
                idx = int(self.enemy_anim_timer * 5) % len(self.mole_frames)
                frame = self.mole_frames[idx]
                fh = frame.get_height()
                render_queue.append((pos[1] + fh // 2, "enemy", frame, pos, cam_x, cam_y))

        # 3. Collect Enemy indicators (Treant)
        for pos in self.treant_positions:
            if self.treant_frames:
                idx = int(self.enemy_anim_timer * 5) % len(self.treant_frames)
                frame = self.treant_frames[idx]
                fh = frame.get_height()
                render_queue.append((pos[1] + fh // 2, "enemy", frame, pos, cam_x, cam_y))

        # 4. Collect Hero
        hero_frame = self._get_hero_frame()
        if hero_frame:
            fh = hero_frame.get_height()
            render_queue.append((self.pos_y + fh // 2, "hero", hero_frame, cam_x, cam_y))

        # 5. Collect other online players
        if room_data and "players" in room_data:
            for pid, p in room_data["players"].items():
                if pid != local_player_id:
                    pos_x = p.get("position_x", 0.0)
                    pos_y = p.get("position_y", 0.0)
                    color_name = p.get("hero_color", "Verde")
                    anim_name = p.get("anim_name", "idle")
                    facing_right = p.get("facing_right", True)
                    
                    if pid not in self.other_players_anims or self.other_players_anims[pid]["color_name"] != color_name:
                        self._cache_other_player_anims(pid, color_name)
                        
                    frames = self.other_players_anims[pid]["anims"].get(anim_name, [])
                    if frames:
                        idx = int(self.enemy_anim_timer * 6) % len(frames)
                        frame = frames[idx % len(frames)]
                        if anim_name == "side" and not facing_right:
                            frame = pygame.transform.flip(frame, True, False)
                            
                        fh = frame.get_height()
                        render_queue.append((pos_y + fh // 2, "other_player", frame, pos_x, pos_y, p))

        # Sort all elements by their Y-base coordinate
        render_queue.sort(key=lambda item: item[0])

        # Draw sorted elements
        for item in render_queue:
            obj_type = item[1]
            if obj_type == "sanctuary":
                _, _, s_data, sx, sy, g_t = item
                self._draw_sanctuary_sprite(screen, s_data, sx, sy, g_t)
            elif obj_type == "dec":
                _, _, img, dx, dy = item
                screen.blit(img, (dx, dy))
            elif obj_type == "enemy":
                _, _, frame, pos, cx, cy = item
                wx, wy = pos
                sx = int(wx - cx)
                sy = int(wy - cy)
                if -64 < sx < SCREEN_W+64 and -64 < sy < SCREEN_H+64:
                    rect = frame.get_rect(center=(sx, sy))
                    screen.blit(frame, rect)
            elif obj_type == "hero":
                _, _, frame, cx, cy = item
                hx = int(self.pos_x - cx)
                hy = int(self.pos_y - cy)
                rect = frame.get_rect(center=(hx, hy))
                screen.blit(frame, rect)
            elif obj_type == "other_player":
                _, _, frame, ox, oy, p = item
                osx = int(ox - cam_x)
                osy = int(oy - cam_y)
                if -64 < osx < SCREEN_W + 64 and -64 < osy < SCREEN_H + 64:
                    rect = frame.get_rect(center=(osx, osy))
                    screen.blit(frame, rect)
                    p_name = p.get("player_name", "Jugador")
                    p_level = p.get("hero_level", 1)
                    p_color_name = p.get("hero_color", "Verde")
                    text = f"{p_name} (Lvl {p_level})"
                    self._draw_floating_label(screen, self.font_hp, text, osx, osy - 50, self._get_color_rgb(p_color_name))

        # ── Floating labels system (drawn on top of all decorations) ────
        for s in self.sanctuaries:
            sx = int(s["wx"] - cam_x)
            sy = int(s["wy"] - cam_y)
            # Only draw if on screen and hero is within 150px
            if -100 < sx < SCREEN_W + 100 and -100 < sy < SCREEN_H + 100:
                dist = math.hypot(self.pos_x - s["wx"], self.pos_y - s["wy"])
                if dist <= 150:
                    img = self.dec_imgs.get("rock_big")
                    label_h = (img.get_height() if img else 38)
                    
                    if s["completed"]:
                        text = "Completado"
                        col = (120, 220, 120)
                    else:
                        text = "Santuario"
                        col = (130, 200, 255)
                    
                    float_y = int(3 * math.sin(self._sanctuary_glow_timer * 2))
                    ly = sy - label_h - 22 + float_y
                    
                    self._draw_floating_label(screen, self.font_hp, text, sx, ly, col)

        # ── Sanctuary approach panel (drawn above world, below HUD) ────
        if self.show_sanctuary_panel:
            self._draw_sanctuary_panel(screen)

        # ── Sanctuary minigame overlay ─────────────────────────
        if self.sanctuary_minigame is not None:
            self.sanctuary_minigame.draw(screen)

        # ── Layer 5b: Leaf particles ───────────────────────────────────────
        for p in self.leaf_particles:
            px = int(p["x"] - cam_x)
            py = int(p["y"] - cam_y)
            if -32 <= px < SCREEN_W+32 and -32 <= py < SCREEN_H+32:
                sz  = p["size"]
                ps  = pygame.Surface((sz*2, sz*2), pygame.SRCALPHA)
                a   = int(120 + 60*math.sin(self.water_timer*2 + p["phase"]))
                col = (*p["color"], max(0, min(255, a)))
                pygame.draw.circle(ps, col, (sz, sz), sz)
                screen.blit(ps, (px-sz, py-sz))

        # ── Layer 6: HUD ──────────────────────────────────────────────────
        bar_h = 32
        bar_y = SCREEN_H - bar_h
        panel_bg = pygame.Surface((SCREEN_W, bar_h), pygame.SRCALPHA)
        panel_bg.fill((8, 5, 18, 210))
        screen.blit(panel_bg, (0, bar_y))
        pygame.draw.line(screen, (90, 70, 180), (0, bar_y), (SCREEN_W, bar_y), 1)

        screen.blit(self.font_panel.render("MAPA MUNDI", True, (255,200,0)), (14, bar_y+8))
        screen.blit(self.font_panel.render(
            f"Pasos: {self.steps}  –  Usa FLECHAS para caminar",
            True, (190,190,210)), (180, bar_y+8))
        screen.blit(self.font_panel.render(
            f"NIVEL: {self.hero.hero_level}", True, (140,255,140)), (650, bar_y+8))

        # HP bar
        hp_bg = pygame.Surface((210, 32), pygame.SRCALPHA)
        hp_bg.fill((8, 5, 18, 200))
        screen.blit(hp_bg, (4, 4))
        pygame.draw.rect(screen, (75, 55, 155), (4, 4, 210, 32), 1)
        hp_ratio  = max(0.0, self.hero.hp / self.hero.max_hp)
        bar_color = (45, 195, 75) if hp_ratio > 0.3 else (200, 48, 48)
        pygame.draw.rect(screen, (28, 0, 0), (9, 9, 200, 20))
        pygame.draw.rect(screen, bar_color, (9, 9, int(200*hp_ratio), 20))
        text_hp = self.font_hp.render(
            f"HP  {self.hero.hp}/{self.hero.max_hp}", True, (255,255,255))
        screen.blit(text_hp, (109 - text_hp.get_width()//2,
                               19 - text_hp.get_height()//2))

        # Name Tag next to HP bar
        name_bg = pygame.Surface((200, 32), pygame.SRCALPHA)
        name_bg.fill((8, 5, 18, 200))
        screen.blit(name_bg, (220, 4))
        pygame.draw.rect(screen, (75, 55, 155), (220, 4, 200, 32), 1)
        name_text = self.font_panel.render(f"HÉROE: {self.hero.name}", True, (100, 180, 255))
        screen.blit(name_text, (230, 20 - name_text.get_height() // 2))

        # EXP bar next to Name Tag
        exp_bg = pygame.Surface((220, 32), pygame.SRCALPHA)
        exp_bg.fill((8, 5, 18, 200))
        screen.blit(exp_bg, (428, 4))
        pygame.draw.rect(screen, (75, 55, 155), (428, 4, 220, 32), 1)
        exp_ratio = max(0.0, min(1.0, self.hero.hero_exp / self.hero.exp_to_next_level))
        pygame.draw.rect(screen, (20, 15, 40), (433, 9, 210, 22))
        pygame.draw.rect(screen, (200, 160, 45), (433, 9, int(210*exp_ratio), 22))
        text_exp = self.font_hp.render(
            f"NV {self.hero.hero_level} – EXP {self.hero.hero_exp}/{self.hero.exp_to_next_level}", True, (255, 255, 255))
        screen.blit(text_exp, (538 - text_exp.get_width()//2,
                               20 - text_exp.get_height()//2))

        # ── Encounter confirmation panel (drawn last, on top) ───────────
        if self.show_encounter_panel:
            self._draw_encounter_panel(screen)

    # -----------------------------------------------------------------------
    # Sanctuary sprite drawing
    # -----------------------------------------------------------------------
    def _draw_sanctuary_sprite(self, screen, s_data, sx, sy, glow_t):
        """Draw a sanctuary object with animated glow (blue if active, grey if completed)."""
        completed = s_data["completed"]

        # ── Base stone shape ────────────────────────────────────────────
        # Use rock-monument image if available, else draw procedural stone
        img = self.dec_imgs.get("rock_big")
        if img is not None:
            # Tint completed ones grey; active ones keep colour
            if completed:
                tinted = img.copy()
                grey = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
                grey.fill((80, 80, 80, 140))
                tinted.blit(grey, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(tinted, (sx - tinted.get_width() // 2, sy - tinted.get_height()))
            else:
                screen.blit(img, (sx - img.get_width() // 2, sy - img.get_height()))
        else:
            # Procedural stone fallback
            stone_col = (90, 90, 110) if completed else (110, 110, 140)
            pygame.draw.ellipse(screen, stone_col,
                                pygame.Rect(sx - 20, sy - 36, 40, 36))
            pygame.draw.ellipse(screen, (60, 60, 80),
                                pygame.Rect(sx - 20, sy - 36, 40, 36), 2)

        if completed:
            return

        # ── Animated glow ring ───────────────────────────────────────────
        glow_r = int(28 + 8 * math.sin(glow_t * 3))
        glow_a = int(90 + 60 * math.sin(glow_t * 2.5))
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (80, 160, 255, max(0, min(255, glow_a))),
                           (glow_r + 2, glow_r + 2), glow_r, 3)
        screen.blit(glow_surf, (sx - glow_r - 2, sy - (img.get_height() if img else 36) // 2 - glow_r - 2))

    def _draw_floating_label(self, screen, font, text, cx, cy, text_color=(255, 255, 255)):
        """Draw a beautiful floating label with dark semi-transparent bg, light border, and text shadow."""
        text_surf = font.render(text, True, text_color)
        shadow_surf = font.render(text, True, (0, 0, 0))
        
        tw, th = text_surf.get_width(), text_surf.get_height()
        pad_x, pad_y = 10, 6
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        
        bx = cx - box_w // 2
        by = cy - box_h // 2
        
        # 1. Background
        box_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        box_surf.fill((10, 5, 20, 200))  # dark semi-transparent
        screen.blit(box_surf, (bx, by))
        
        # 2. Light border
        pygame.draw.rect(screen, (100, 160, 255), (bx, by, box_w, box_h), 1, border_radius=4)
        
        # 3. Text shadow (offset by 1px)
        screen.blit(shadow_surf, (bx + pad_x + 1, by + pad_y + 1))
        
        # 4. Main text
        screen.blit(text_surf, (bx + pad_x, by + pad_y))

    def _get_color_rgb(self, color_name):
        colors_available = [
            {"name": "Verde",    "rgb": (60, 200, 100)},
            {"name": "Azul",     "rgb": (60, 120, 220)},
            {"name": "Rojo",     "rgb": (220, 60, 60)},
            {"name": "Morado",   "rgb": (150, 80, 220)},
            {"name": "Amarillo", "rgb": (240, 220, 50)},
            {"name": "Naranja",  "rgb": (240, 130, 40)}
        ]
        for c in colors_available:
            if c["name"] == color_name:
                return c["rgb"]
        return (255, 255, 255)

    def _cache_other_player_anims(self, player_id, color_name):
        rgb = self._get_color_rgb(color_name)
        hero_dir = FOREST / "spritesheets" / "hero"
        anims = {}
        anims["idle"]  = [_tint_sprite_surface(f, rgb) for f in _load_sheet(hero_dir/"idle"/"hero-idle-front.png", 32,32,1, scale=2)]
        anims["front"] = [_tint_sprite_surface(f, rgb) for f in _load_sheet(hero_dir/"walk"/"hero-walk-front.png", 32,32,6, scale=2)]
        anims["side"]  = [_tint_sprite_surface(f, rgb) for f in _load_sheet(hero_dir/"walk"/"hero-walk-side.png",  32,32,6, scale=2)]
        anims["back"]  = [_tint_sprite_surface(f, rgb) for f in _load_sheet(hero_dir/"walk"/"hero-back-walk.png",  32,32,6, scale=2)]
        
        self.other_players_anims[player_id] = {
            "color_name": color_name,
            "anims": anims
        }
