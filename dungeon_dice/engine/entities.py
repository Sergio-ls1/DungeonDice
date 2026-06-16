import pygame
import os
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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Entity:
    def __init__(self, name, hp, mp, max_hp, max_mp, image_path, frame_width, frame_height, num_frames=1, scale=1.0, flip=False):
        self.name = name
        self.hp = hp
        self.mp = mp
        self.max_hp = max_hp
        self.max_mp = max_mp
        self.level = 1
        
        self.frames = []
        self.current_frame = 0
        self.anim_timer = 0
        self.anim_speed = 0.1
        self.flip = flip
        
        if image_path:
            res_image = resource_path(image_path)
            if os.path.exists(res_image):
                try:
                    sprite_sheet = pygame.image.load(res_image).convert_alpha()
                    for i in range(num_frames):
                        frame = pygame.Surface((frame_width, frame_height), pygame.SRCALPHA)
                        frame.blit(sprite_sheet, (0, 0), (i * frame_width, 0, frame_width, frame_height))
                        
                        if flip:
                            frame = pygame.transform.flip(frame, True, False)
                            
                        scaled = pygame.transform.scale(frame, (int(frame_width * scale), int(frame_height * scale)))
                        self.frames.append(scaled)
                except Exception as e:
                    print(f"Error loading {image_path}: {e}")

        if not self.frames:
            surf = pygame.Surface((64, 64))
            surf.fill((255, 0, 255))
            self.frames.append(surf)

    def draw_sprite(self, screen, x, y, size_param_ignored=None):
        """Draw the sprite with its feet at (x, y).
        x  – horizontal centre of the sprite
        y  – floor / feet Y coordinate
        """
        if not self.frames:
            return
            
        self.anim_timer += 1/60.0
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            
        frame = self.frames[self.current_frame]
        
        # Place the sprite so its bottom edge is at y and it is centred on x.
        draw_x = x - frame.get_width() // 2
        draw_y = y - frame.get_height()
        
        screen.blit(frame, (draw_x, draw_y))


class Hero(Entity):
    def __init__(self):
        # 10 frames of 128x128
        sheets_dir = os.path.join(BASE_DIR, "..", "..", "assets", "male_hero_free", "individual_sheets")
        idle_path = os.path.join(sheets_dir, "male_hero-idle.png")
        super().__init__("Héroe", 50, 50, 50, 50, idle_path, 128, 128, 10, scale=2.5, flip=False)

        self.state = "IDLE"
        self.animations = {}
        self.animations["IDLE"] = list(self.frames) # fallback
        self.shield = 0
        self.completed_sanctuaries = []   # list of sanctuary indices already completed
        self.hero_level = 1
        self.hero_exp = 0
        self.exp_to_next_level = 100
        self.max_shield = 20
        self.level = self.hero_level
        self.pending_level_ups = []
        self.creation_date = ""
        self.last_saved_date = ""
        self.play_time = 0.0
        self.hero_color_name = "Rojo"
        self.hero_color_rgb = (220, 60, 60)
        self.current_save_path = ""

        run_path = os.path.join(sheets_dir, "male_hero-run.png")
        attack_path = os.path.join(sheets_dir, "male_hero-attack_1.png")

        self.load_animation("IDLE", idle_path, 128, 128, 10, scale=2.5, flip=False)
        self.load_animation("RUN_R", run_path, 128, 128, 8, scale=2.5, flip=False)
        self.load_animation("RUN_L", run_path, 128, 128, 8, scale=2.5, flip=True)
        self.load_animation("ATTACK", attack_path, 128, 128, 6, scale=2.5, flip=False)

    def load_animation(self, key, path, frame_w, frame_h, num_frames, scale=1.5, flip=False):
        if not path:
            return
        res_path = resource_path(path)
        if not os.path.exists(res_path):
            return
        self.animations[key] = []
        try:
            sprite_sheet = pygame.image.load(res_path).convert_alpha()
            for i in range(num_frames):
                frame = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
                frame.blit(sprite_sheet, (0, 0), (i * frame_w, 0, frame_w, frame_h))
                if flip:
                    frame = pygame.transform.flip(frame, True, False)
                scaled = pygame.transform.scale(frame, (int(frame_w * scale), int(frame_h * scale)))
                self.animations[key].append(scaled)
        except Exception as e:
            print(f"Error loading {path} for {key}: {e}")

    def draw_sprite(self, screen, x, y, size_param_ignored=None):
        frames_list = self.animations.get(self.state)
        if not frames_list or len(frames_list) == 0:
            frames_list = self.animations.get("IDLE")
        if not frames_list:
            return

        self.anim_timer += 1/60.0
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0
            self.current_frame = (self.current_frame + 1) % len(frames_list)

        frame = frames_list[self.current_frame % len(frames_list)]
        draw_x = x - frame.get_width() // 2
        draw_y = y - frame.get_height()
        screen.blit(frame, (draw_x, draw_y))

    def set_state(self, new_state):
        if new_state != self.state:
            self.state = new_state
            self.current_frame = 0

    def add_exp(self, amount):
        self.hero_exp += amount
        while self.hero_exp >= self.exp_to_next_level:
            self.hero_exp -= self.exp_to_next_level
            self.hero_level += 1
            self.level = self.hero_level
            self.max_hp += 10
            self.hp += 10
            self.max_shield += 5
            self.exp_to_next_level = self.hero_level * 100
            self.pending_level_ups.append(self.hero_level)

    def get_data(self):
        return {
            "hp": self.hp,
            "mp": self.mp,
            "max_hp": self.max_hp,
            "max_mp": self.max_mp,
            "level": self.level,
            "name": self.name,
            "shield": self.shield,
            "completed_sanctuaries": list(self.completed_sanctuaries),
            "hero_level": self.hero_level,
            "hero_exp": self.hero_exp,
            "exp_to_next_level": self.exp_to_next_level,
            "max_shield": self.max_shield,
            "creation_date": self.creation_date,
            "last_saved_date": self.last_saved_date,
            "play_time": self.play_time,
            "hero_color_name": self.hero_color_name,
            "hero_color_rgb": self.hero_color_rgb,
            "current_save_path": self.current_save_path,
        }

    def load_data(self, data):
        self.hp = data.get("hp", 50)
        self.mp = data.get("mp", 50)
        self.max_hp = data.get("max_hp", 50)
        self.max_mp = data.get("max_mp", 50)
        self.level = data.get("level", 1)
        self.name = data.get("name", "Héroe")
        self.shield = data.get("shield", 0)
        self.completed_sanctuaries = data.get("completed_sanctuaries", [])
        self.hero_level = data.get("hero_level", self.level)
        self.hero_exp = data.get("hero_exp", 0)
        self.exp_to_next_level = data.get("exp_to_next_level", self.hero_level * 100)
        self.max_shield = data.get("max_shield", 20)
        self.level = self.hero_level
        self.creation_date = data.get("creation_date", "")
        self.last_saved_date = data.get("last_saved_date", "")
        self.play_time = data.get("play_time", 0.0)
        self.hero_color_name = data.get("hero_color_name", "Rojo")
        self.hero_color_rgb = tuple(data.get("hero_color_rgb", [220, 60, 60]))
        self.current_save_path = data.get("current_save_path", "")


class Enemy(Entity):
    def __init__(self, level=1):
        hp = 30 + level * 10
        # 4 frames of 64x80 (Idle-Sheet.png)
        path = os.path.join(BASE_DIR, "..", "..", "assets", "Legacy-Fantasy - High Forest 2.3", "Character", "Idle", "Idle-Sheet.png")
        super().__init__(f"Villano Lv{level}", hp, 0, hp, 0, path, 64, 80, 4, scale=3.0, flip=True)
        self.level = level
