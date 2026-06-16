import pygame
import random
import os
import math
from pathlib import Path
from .dice import Dice
from .cards import get_cards_for_roll, Card

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_FOREST   = Path(BASE_DIR).parents[1] / "tiny-RPG-forest-files" / "tiny-RPG-forest-files" / "Assets" / "PNG"
_SRC_TILE = 16
_TILE     = 32


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


def _load_sheet_b(path, fw, fh, nf, scale=1):
    """Load a horizontal spritesheet. Returns [] if file missing."""
    frames = []
    res_path = resource_path(path)
    if not os.path.exists(res_path):
        return frames
    sheet = pygame.image.load(res_path).convert_alpha()
    sw, sh = sheet.get_size()
    actual = min(nf, sw // fw)
    for i in range(actual):
        r = pygame.Rect(i*fw, 0, fw, fh)
        if r.right <= sw and r.bottom <= sh:
            f = sheet.subsurface(r).copy()
            if scale != 1:
                w, h = f.get_size()
                f = pygame.transform.scale(f, (int(w*scale), int(h*scale)))
            frames.append(f)
    return frames


def _build_arena_bg(tileset_path, arena_w, arena_h):
    """Build a tiled forest background for the battle arena."""
    surf = pygame.Surface((arena_w, arena_h))
    surf.fill((35, 65, 22))          # fallback grass green

    res_tileset = resource_path(tileset_path)
    if not os.path.exists(res_tileset):
        return surf

    try:
        tileset = pygame.image.load(res_tileset).convert_alpha()
        tw, th  = tileset.get_size()

        def ext(col, row):
            px, py = col*_SRC_TILE, row*_SRC_TILE
            r = pygame.Rect(px, py, _SRC_TILE, _SRC_TILE)
            if r.right <= tw and r.bottom <= th:
                return pygame.transform.scale(
                    tileset.subsurface(r).copy(), (_TILE, _TILE))
            return None

        # Use a mix of grass and path tiles for a natural arena floor
        grass_tiles = [t for t in [ext(18,0),ext(19,0),ext(20,0),ext(18,1),ext(19,1)] if t]
        path_tiles  = [t for t in [ext(18,3),ext(19,3),ext(20,3),ext(18,4)]           if t]

        if not grass_tiles:
            return surf

        rng = random.Random(7)
        cols = math.ceil(arena_w / _TILE) + 1
        rows = math.ceil(arena_h / _TILE) + 1
        for row in range(rows):
            for col in range(cols):
                # Horizontal path where characters are standing (rows 11 to 13)
                if 11 <= row <= 13:
                    if path_tiles and rng.random() < 0.70:
                        tile = rng.choice(path_tiles)
                    else:
                        tile = rng.choice(grass_tiles)
                else:
                    if path_tiles and rng.random() < 0.08:
                        tile = rng.choice(path_tiles)
                    else:
                        tile = rng.choice(grass_tiles)
                surf.blit(tile, (col*_TILE, row*_TILE))

        # Dark vignette at edges to frame the arena
        for i in range(25):
            alpha = int(140 * (1 - i/25))
            vign  = pygame.Surface((arena_w, 1), pygame.SRCALPHA)
            vign.fill((0, 0, 0, alpha))
            surf.blit(vign, (0, i))
            surf.blit(vign, (0, arena_h-1-i))
    except Exception:
        pass

    return surf


class BattleSystem:
    def __init__(self, hero, enemy, is_multiplayer=False):
        self.hero = hero
        self.enemy = enemy
        self.is_multiplayer = is_multiplayer
        self.dice1 = Dice(378, 518)
        self.dice2 = Dice(378, 518)
        self.dice = self.dice1
        self.selected_dice_count = 0
        self.dice_processed = False
        self.double_roll_effect_text = ""
        self.legendary_win_delay = 0.0
        
        # Variables de PANTALLAZO AZUL
        self.blue_screen_active = False
        self.blue_screen_timer = 15.0
        self.blue_screen_question = None
        self.blue_screen_state = "QUESTION"
        self.blue_screen_selected_opt = None
        
        self.timer = 40.0
        self.turn = "HERO"
        self.message_log = ["¡Batalla iniciada!", f"Te enfrentas a {enemy.name}."]
        self.dice_value = 0
        self.hand = []
        self.actions_left = 0
        self.combo_mode = False
        self.blink_timer = 0.0
        self.enemy_stunned = False
        self.enemy_poison = 0
        self.hero_regen = 0
        self.shield_pct = 0.0
        self.log_scroll = 0
        self.paused = False
        self.show_pause_menu = False
        self.exit_to_menu = False
        self.restart_game = False
        
        # ── Visual setup (sprites + side-view arena assets) ────────────────
        mountain_path = _FOREST.parents[1] / "Tiny RPG Mountain Files" / "Tiny RPG Mountain Files" / "png" / "tileset.png"
        self.mountain_grass_tile = None
        res_mountain = resource_path(mountain_path)
        if os.path.exists(res_mountain):
            try:
                sheet = pygame.image.load(res_mountain).convert_alpha()
                # Extract grass tile at x=16, y=0 (16x16) and scale it to 32x32
                tile_rect = pygame.Rect(16, 0, 16, 16)
                self.mountain_grass_tile = pygame.transform.scale(
                    sheet.subsurface(tile_rect).copy(), (32, 32)
                )
            except Exception as e:
                print(f"Error loading mountain grass tile: {e}")

        # Hero idle sprite (tiny-RPG, side view)
        hero_idle = _load_sheet_b(
            _FOREST/"spritesheets"/"hero"/"idle"/"hero-idle-side.png",
            32, 32, 1, scale=4)
        self._battle_hero_frames = hero_idle if hero_idle else []
        self._battle_hero_timer  = 0.0
        self._battle_hero_idx    = 0

        # Enemy sprite: pick mole or treant by level parity (side view)
        if enemy.level % 2 == 0:
            enemy_frames = _load_sheet_b(
                _FOREST/"spritesheets"/"treant"/"idle"/"treant-idle-side.png",
                31, 35, 1, scale=4)
        else:
            enemy_frames = _load_sheet_b(
                _FOREST/"spritesheets"/"mole"/"idle"/"mole-idle-side.png",
                24, 24, 1, scale=4)
        self._battle_enemy_frames = enemy_frames if enemy_frames else []
        self._battle_enemy_timer  = 0.0
        self._battle_enemy_idx    = 0

        # Decoration overlays (trees, bushes, rocks) for the arena
        sliced = _FOREST / "environment" / "sliced-objects"
        self.dec_imgs = {}
        defs = {
            "tree_orange": (sliced/"tree-orange.png",   2.0),
            "tree_pink":   (sliced/"tree-pink.png",     2.0),
            "rock":        (sliced/"rock.png",          1.6),
            "rock_big":    (sliced/"rock-monument.png", 1.3),
            "bush":        (sliced/"bush.png",          1.6),
            "bush_tall":   (sliced/"bush-tall.png",     1.6),
        }
        for key, (p, scale) in defs.items():
            res_p = resource_path(p)
            if os.path.exists(res_p):
                img = pygame.image.load(res_p).convert_alpha()
                w, h = img.get_size()
                self.dec_imgs[key] = pygame.transform.scale(img, (int(w*scale), int(h*scale)))

        self.arena_decorations = [
            # Left side decorations (rooted on ground y = 360)
            ("tree_orange", 50, 365),
            ("tree_pink", 110, 360),
            ("bush_tall", 170, 370),
            ("rock", 60, 365),
            
            # Right side decorations (rooted on ground y = 360)
            ("tree_pink", 834, 365),
            ("tree_orange", 774, 360),
            ("bush", 714, 370),
            ("rock_big", 814, 370),
        ]
        self.arena_decorations.sort(key=lambda d: d[2])

    def layout_cards(self, num_cards, box_x=480, box_w=394, box_h=170, max_w=115, max_h=160):
        if num_cards == 0:
            return []
            
        min_gap = 6
        if num_cards * max_w + (num_cards - 1) * min_gap <= box_w:
            w = max_w
            h = max_h
            if num_cards > 1:
                desired_gap = 16
                if num_cards * w + (num_cards - 1) * desired_gap > box_w:
                    gap = (box_w - num_cards * w) // (num_cards - 1)
                else:
                    gap = desired_gap
            else:
                gap = 0
            actual_total_w = num_cards * w + (num_cards - 1) * gap
            start_x = box_x + (box_w - actual_total_w) // 2
        else:
            gap = 6
            w = (box_w - (num_cards - 1) * gap) // num_cards
            h = int(w * (max_h / max_w))
            if h > box_h:
                h = box_h
                w = int(h * (max_w / max_h))
            actual_total_w = num_cards * w + (num_cards - 1) * gap
            start_x = box_x + (box_w - actual_total_w) // 2
            
        positions = []
        y = 460 + (180 - h) // 2
        for i in range(num_cards):
            positions.append((start_x + i * (w + gap), y, w, h))
        return positions

    def update_card_rects(self):
        positions = self.layout_cards(len(self.hand))
        for i, card in enumerate(self.hand):
            cx, cy, cw, ch = positions[i]
            card.rect.x = cx
            card.rect.y = cy
            card.rect.width = cw
            card.rect.height = ch
        
    def log(self, msg):
        self.message_log.append(msg)
        if len(self.message_log) > 50:
            self.message_log.pop(0)

    def handle_event(self, event):
        self.update_card_rects()
        
        # Procesar eventos de PANTALLAZO AZUL
        if self.blue_screen_active:
            if self.blue_screen_state == "QUESTION":
                if event.type == pygame.KEYDOWN:
                    key_map = {
                        pygame.K_a: 0, pygame.K_b: 1,
                        pygame.K_c: 2, pygame.K_d: 3,
                        pygame.K_1: 0, pygame.K_2: 1,
                        pygame.K_3: 2, pygame.K_4: 3,
                    }
                    if event.key in key_map:
                        self._answer_blue_screen(key_map[event.key])
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, rect in enumerate(self._blue_screen_option_rects()):
                        if rect.collidepoint(event.pos):
                            self._answer_blue_screen(i)
                            break
            elif self.blue_screen_state in ("SUCCESS", "FAIL", "TIMEOUT"):
                if event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_RETURN, pygame.K_KP_ENTER,
                        pygame.K_SPACE, pygame.K_ESCAPE):
                    self._close_blue_screen()
            return

        # Pause button and scroll are always checked
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if pygame.Rect(834, 5, 45, 30).collidepoint(event.pos):
                self.show_pause_menu = not self.show_pause_menu
                return

        if self.show_pause_menu:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # REANUDAR: y=270, button rect (292, 265, 300, 40)
                if pygame.Rect(292, 265, 300, 40).collidepoint(event.pos):
                    self.show_pause_menu = False
                # EMPEZAR DE NUEVO: y=330, button rect (292, 325, 300, 40)
                elif pygame.Rect(292, 325, 300, 40).collidepoint(event.pos):
                    self.show_pause_menu = False
                    self.restart_game = True
                # SALIR AL MENÚ: y=390, button rect (292, 385, 300, 40)
                elif pygame.Rect(292, 385, 300, 40).collidepoint(event.pos):
                    self.show_pause_menu = False
                    self.exit_to_menu = True
            return

        if event.type == pygame.MOUSEWHEEL:
            area_log = pygame.Rect(10, 470, 320, 160)
            if area_log.collidepoint(pygame.mouse.get_pos()):
                self.log_scroll -= event.y
                if hasattr(self, 'wrapped_log'):
                    max_scroll = max(0, len(self.wrapped_log) - 6)
                    self.log_scroll = max(0, min(self.log_scroll, max_scroll))

        if self.turn != "HERO": return
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mouse_pos = event.pos
                
                # Clic en los botones de lanzar
                if self.actions_left == 0 and not self.hand and self.selected_dice_count == 0:
                    btn_single = pygame.Rect(487, 485, 240, 45)
                    btn_double = pygame.Rect(487, 545, 240, 45)
                    if btn_single.collidepoint(mouse_pos):
                        self.selected_dice_count = 1
                        self.dice1.rect.x = 381
                        self.dice1.rect.y = 530
                        self.dice1.roll()
                        self.dice_processed = False
                    elif btn_double.collidepoint(mouse_pos):
                        # 25% de probabilidad de PANTALLAZO AZUL en multijugador
                        if self.is_multiplayer and random.random() < 0.25:
                            self._trigger_blue_screen()
                        else:
                            self.selected_dice_count = 2
                            self.dice1.rect.x = 345
                            self.dice1.rect.y = 530
                            self.dice2.rect.x = 417
                            self.dice2.rect.y = 530
                            self.dice1.roll()
                            self.dice2.roll()
                            self.dice_processed = False
                    
                # Clic en cartas
                is_rolling = self.dice1.rolling or (self.selected_dice_count == 2 and self.dice2.rolling)
                if not is_rolling and self.actions_left > 0 and self.hand:
                    for i, card in enumerate(self.hand):
                        if card.rect.collidepoint(mouse_pos):
                            self.play_card(i)
                            break

    def apply_card(self, card):
        # Efecto de daño
        dmg = 0
        if card.card_type in ["attack", "strong"]:
            dmg = card.value
            if card.effect == "ignore_def":
                # Si tuviéramos un stat DEF en el enemigo, aquí lo ignoramos
                pass
            self.enemy.hp -= dmg
            self.log(f"Infliges {dmg} de daño.")

        # Efecto de curación
        if card.card_type == "heal":
            heal = card.value
            self.hero.hp = min(self.hero.max_hp, self.hero.hp + heal)
            self.log(f"Te curas {heal} HP.")
            if card.effect == "regen_5_2":
                self.hero_regen = 2
            elif card.effect == "restore_10_mp":
                self.hero.mp = min(self.hero.max_mp, self.hero.mp + 10)
                self.log("Restauras 10 MP.")

        # Efectos especiales
        if card.card_type == "special":
            if card.effect == "skip_both":
                self.log("¡Tropiezas! Pierdes tu turno y el enemigo no ataca.")
                self.enemy_stunned = True
            elif card.effect == "shield_30":
                self.shield_pct = 0.30
                self.log("Ganas un escudo del 30%.")
            elif card.effect == "shield_60":
                self.shield_pct = 0.60
                self.log("Ganas un escudo del 60%.")
            elif card.effect == "poison_4_2":
                self.enemy_poison = 2
                self.log("Envenenas al enemigo.")
            elif card.effect == "stun_1":
                self.enemy_stunned = True
                self.log("¡Golpe paralizante! Enemigo aturdido.")

    def play_card(self, index):
        card = self.hand.pop(index)
        self.log(f"Juegas {card.name}")
        
        self.apply_card(card)
        
        self.actions_left -= 1
        
        self.update_card_rects()
        
        if self.enemy.hp <= 0:
            self.log("¡Enemigo derrotado!")
            self.timer = 0
        elif self.actions_left <= 0:
            self.end_hero_turn()

    def end_hero_turn(self):
        self.hand = []
        self.turn = "ENEMY"
        self.timer = 40.0
        self.log("Turno del enemigo.")

    def update(self, dt):
        if self.show_pause_menu:
            return
            
        # Actualización de PANTALLAZO AZUL
        if hasattr(self, 'blue_screen_active') and self.blue_screen_active:
            if self.blue_screen_state == "QUESTION":
                self.blue_screen_timer -= dt
                if self.blue_screen_timer <= 0:
                    self.blue_screen_timer = 0
                    self.blue_screen_state = "TIMEOUT"
            return

        self.blink_timer += dt
        
        # Decrementar el delay de victoria legendaria
        if hasattr(self, 'legendary_win_delay') and self.legendary_win_delay > 0:
            self.legendary_win_delay -= dt
            if self.legendary_win_delay <= 0:
                self.enemy.hp = 0
        
        # Actualización de dados
        if self.selected_dice_count == 1:
            if self.dice1.rolling:
                res = self.dice1.update(dt)
                if res is not None and not self.dice_processed:
                    self.dice_processed = True
                    self.dice_value = res
                    self.log(f"¡El dado muestra un {res}!")
                    self.hand = get_cards_for_roll(res)
                    if res == 6:
                        self.actions_left = 2
                        self.combo_mode = True
                    else:
                        self.actions_left = 1
                        self.combo_mode = False
        elif self.selected_dice_count == 2:
            if self.dice1.rolling or self.dice2.rolling:
                self.dice1.update(dt)
                self.dice2.update(dt)
                if not self.dice1.rolling and not self.dice2.rolling and not self.dice_processed:
                    self.dice_processed = True
                    res1 = self.dice1.value
                    res2 = self.dice2.value
                    total = res1 + res2
                    self.dice_value = total
                    self.log(f"Dado 1 = {res1}")
                    self.log(f"Dado de Riesgo = {res2}")
                    self.log(f"Total = {total}")
                    
                    self.hand = get_cards_for_roll(res1)
                    if res1 == 6:
                        self.actions_left = 2
                        self.combo_mode = True
                    else:
                        self.actions_left = 1
                        self.combo_mode = False
                        
                    # Aplicar efectos especiales del Doble Dado
                    if res1 == 6 and res2 == 6:
                        self.double_roll_effect_text = "¡CRÍTICO LEGENDARIO!"
                        self.log("¡CRÍTICO LEGENDARIO! Victoria instantánea.")
                        self.legendary_win_delay = 1.5
                    elif total in (10, 11):
                        effect = random.choice(["hp", "shield", "crit"])
                        if effect == "hp":
                            self.hero.hp = min(self.hero.max_hp + 10, self.hero.hp + 10)
                            self.double_roll_effect_text = "¡Resultado Alto: +10 HP temporal!"
                            self.log("¡Resultado Alto! Obtienes +10 HP temporal.")
                        elif effect == "shield":
                            self.hero.shield = min(self.hero.max_shield, self.hero.shield + 5)
                            self.double_roll_effect_text = "¡Resultado Alto: +5 Escudo!"
                            self.log("¡Resultado Alto! Ganas +5 de Escudo.")
                        elif effect == "crit":
                            self.enemy.hp = max(0, self.enemy.hp - 20)
                            self.double_roll_effect_text = "¡Resultado Alto: +20 Daño Crítico!"
                            self.log("¡Resultado Alto! Infliges 20 de daño crítico adicional.")
                    elif total in (7, 8, 9):
                        self.double_roll_effect_text = "Resultado Medio: Sin efecto"
                        self.log("Resultado medio: La batalla continúa normalmente.")
                    elif total in (2, 3, 4, 5, 6):
                        penalty = random.choice(["hp10", "hp15", "shield5", "lose_turn"])
                        if penalty == "hp10":
                            self.hero.hp = max(0, self.hero.hp - 10)
                            self.double_roll_effect_text = "¡Resultado Bajo: -10 HP!"
                            self.log("¡Resultado Bajo! Penalización: pierdes 10 HP.")
                        elif penalty == "hp15":
                            self.hero.hp = max(0, self.hero.hp - 15)
                            self.double_roll_effect_text = "¡Resultado Bajo: -15 HP!"
                            self.log("¡Resultado Bajo! Penalización: pierdes 15 HP.")
                        elif penalty == "shield5":
                            self.hero.shield = max(0, self.hero.shield - 5)
                            self.double_roll_effect_text = "¡Resultado Bajo: -5 Escudo!"
                            self.log("¡Resultado Bajo! Penalización: pierdes 5 de Escudo.")
                        elif penalty == "lose_turn":
                            self.double_roll_effect_text = "¡Resultado Bajo: Pierdes el turno!"
                            self.log("¡Resultado Bajo! Penalización: pierdes el turno.")
                            self.actions_left = 0
                            self.hand = []
                            self.end_hero_turn()

        if self.turn == "HERO":
            self.timer -= dt
            if self.timer <= 0:
                self.timer = 0
                self.log("¡Tiempo agotado!")
                self.end_hero_turn()
        elif self.turn == "ENEMY":
            self.timer -= dt
            # Retraso para que el enemigo "piense"
            if self.timer <= 38.0:
                # Efectos de inicio de turno
                if self.enemy_poison > 0:
                    self.enemy.hp -= 4
                    self.log("El veneno causa 4 daño.")
                    self.enemy_poison -= 1
                    
                if self.hero_regen > 0:
                    self.hero.hp = min(self.hero.max_hp, self.hero.hp + 5)
                    self.log("Regeneras 5 HP.")
                    self.hero_regen -= 1

                if self.enemy.hp <= 0:
                    self.log("¡Enemigo derrotado por el veneno!")
                    self.timer = 0
                    return

                if self.enemy_stunned:
                    self.log("El enemigo está paralizado y no ataca.")
                    self.enemy_stunned = False
                else:
                    dmg = random.randint(5, 15) + (self.enemy.level * 2)
                    if self.shield_pct > 0:
                        blocked = int(dmg * self.shield_pct)
                        dmg -= blocked
                        self.log(f"Escudo bloquea {blocked} de daño.")
                        self.shield_pct = 0.0 # El escudo se consume
                    
                    self.hero.hp -= dmg
                    self.log(f"El enemigo ataca por {dmg}.")
                    if self.hero.hp < 0: self.hero.hp = 0
                
                self.turn = "HERO"
                self.timer = 40.0
                self.actions_left = 0
                self.dice_value = 0
                self.hand = []
                self.selected_dice_count = 0
                self.dice_processed = False
                self.double_roll_effect_text = ""

    def _trigger_blue_screen(self):
        from .sanctuary import QUESTION_BANK
        allowed_topics = {
            "windows", "linux", "macos", "bios", "drivers", "ascii",
            "hardware", "software", "bus de datos", "periféricos de entrada",
            "periféricos de salida"
        }
        questions = [
            q for q in QUESTION_BANK 
            if q.get("topic", "").lower() in allowed_topics or "periférico" in q.get("topic", "").lower()
        ]
        
        # Select one random question
        q = random.choice(questions)
        
        # Shuffle options
        opts = list(q["opts"])
        correct_t = opts[q["correct"]]
        random.shuffle(opts)
        new_correct = opts.index(correct_t)
        
        self.blue_screen_question = {
            "q": q["q"],
            "opts": opts,
            "correct": new_correct
        }
        
        self.blue_screen_active = True
        self.blue_screen_timer = 15.0
        self.blue_screen_state = "QUESTION"
        self.blue_screen_selected_opt = None

    def _blue_screen_option_rects(self):
        rects = []
        base_y = 280
        for i in range(4):
            rects.append(pygame.Rect(132, base_y + i * 60, 620, 45))
        return rects

    def _answer_blue_screen(self, idx):
        if self.blue_screen_state != "QUESTION":
            return
        self.blue_screen_selected_opt = idx
        correct = self.blue_screen_question["correct"]
        if idx == correct:
            self.blue_screen_state = "SUCCESS"
            self.hero.add_exp(5)
        else:
            self.blue_screen_state = "FAIL"

    def _close_blue_screen(self):
        if self.blue_screen_state == "SUCCESS":
            self.blue_screen_active = False
            # Roll the double dice now!
            self.selected_dice_count = 2
            self.dice1.rect.x = 345
            self.dice1.rect.y = 530
            self.dice2.rect.x = 417
            self.dice2.rect.y = 530
            self.dice1.roll()
            self.dice2.roll()
            self.dice_processed = False
        else:
            # Failure or timeout -> automatic defeat
            self.hero.hp = 0
            self.blue_screen_active = False

    def _wrap_text_bs(self, text, font, max_w):
        words = text.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            if font.size(test)[0] <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines or [text]

    def _draw_msg_screen(self, screen, font_large, font_medium, title, subtitle, color):
        ts = font_large.render(title, True, color)
        screen.blit(ts, (442 - ts.get_width() // 2, 280))
        
        ss = font_medium.render(subtitle, True, (255, 255, 255))
        screen.blit(ss, (442 - ss.get_width() // 2, 360))

    def _draw_blue_screen(self, screen, font_small, font_medium, font_large):
        # 1. Fill background with classic BSOD Blue (0, 0, 170)
        blue_bg = pygame.Surface((884, 640))
        blue_bg.fill((0, 0, 170))
        screen.blit(blue_bg, (0, 0))
        
        # 2. Draw white title header
        title_text = "ERROR CRÍTICO DEL SISTEMA"
        title_surf = font_large.render(title_text, True, (255, 255, 255))
        screen.blit(title_surf, (442 - title_surf.get_width() // 2, 40))
        
        subtitle_text = "Recupera el sistema respondiendo correctamente."
        sub_surf = font_medium.render(subtitle_text, True, (255, 255, 255))
        screen.blit(sub_surf, (442 - sub_surf.get_width() // 2, 95))
        
        # Timer display
        timer_val = int(math.ceil(self.blue_screen_timer))
        timer_text = f"Tiempo restante: {timer_val}"
        timer_surf = font_medium.render(timer_text, True, (255, 255, 0)) # yellow for noticeability
        screen.blit(timer_surf, (442 - timer_surf.get_width() // 2, 130))
        
        pygame.draw.line(screen, (255, 255, 255), (50, 170), (834, 170), 2)
        
        # 3. Draw content depending on state
        if self.blue_screen_state == "QUESTION":
            q = self.blue_screen_question
            
            # Draw Question text wrapped
            q_lines = self._wrap_text_bs(q["q"], font_medium, 720)
            qy = 190
            for line in q_lines:
                q_surf = font_medium.render(line, True, (255, 255, 255))
                screen.blit(q_surf, (442 - q_surf.get_width() // 2, qy))
                qy += q_surf.get_height() + 5
                
            # Draw Options
            letters = ["A", "B", "C", "D"]
            mx, my = pygame.mouse.get_pos()
            for i, rect in enumerate(self._blue_screen_option_rects()):
                hover = rect.collidepoint(mx, my)
                bg_col = (0, 0, 255) if hover else (0, 0, 100) # lighter blue on hover
                border_col = (255, 255, 255)
                
                pygame.draw.rect(screen, bg_col, rect, border_radius=4)
                pygame.draw.rect(screen, border_col, rect, 1, border_radius=4)
                
                # Letter indicator
                let_surf = font_medium.render(letters[i] + ")", True, (255, 255, 255))
                screen.blit(let_surf, (rect.x + 15, rect.centery - let_surf.get_height() // 2))
                
                # Option text
                opt_lines = self._wrap_text_bs(q["opts"][i], font_small, 540)
                oy = rect.centery - (len(opt_lines) * font_small.get_height()) // 2
                for ol in opt_lines:
                    ot = font_small.render(ol, True, (255, 255, 255))
                    screen.blit(ot, (rect.x + 50, oy))
                    oy += font_small.get_height() + 2
                    
        elif self.blue_screen_state == "SUCCESS":
            msg_title = "Sistema recuperado."
            msg_sub = "Presiona ENTER para continuar"
            self._draw_msg_screen(screen, font_large, font_medium, msg_title, msg_sub, (100, 255, 100))
            
        elif self.blue_screen_state == "FAIL":
            msg_title = "Fallo crítico del sistema."
            msg_sub = "Derrota automática. Presiona ENTER para continuar"
            self._draw_msg_screen(screen, font_large, font_medium, msg_title, msg_sub, (255, 100, 100))
            
        elif self.blue_screen_state == "TIMEOUT":
            msg_title = "Tiempo agotado."
            msg_sub = "Derrota automática. Presiona ENTER para continuar"
            self._draw_msg_screen(screen, font_large, font_medium, msg_title, msg_sub, (255, 100, 100))

    def is_over(self):
        return self.hero.hp <= 0 or self.enemy.hp <= 0

    def draw(self, screen, font_small, font_medium, font_large):
        # Dibujar PANTALLAZO AZUL
        if hasattr(self, 'blue_screen_active') and self.blue_screen_active:
            self._draw_blue_screen(screen, font_small, font_medium, font_large)
            return

        # ── Advance battle sprite animation timers (visual only) ───────────
        self._battle_hero_timer  += 1/60.0
        self._battle_enemy_timer += 1/60.0
        if self._battle_hero_timer  >= 0.15 and self._battle_hero_frames:
            self._battle_hero_timer  = 0.0
            self._battle_hero_idx    = (self._battle_hero_idx  + 1) % len(self._battle_hero_frames)
        if self._battle_enemy_timer >= 0.15 and self._battle_enemy_frames:
            self._battle_enemy_timer = 0.0
            self._battle_enemy_idx   = (self._battle_enemy_idx + 1) % len(self._battle_enemy_frames)

        # 1. Cielo (Sky gradient)
        for y_coord in range(0, 360):
            factor = y_coord / 360.0
            r = int(100 + (210 - 100) * factor)
            g = int(145 + (225 - 145) * factor)
            b = int(220 + (255 - 220) * factor)
            pygame.draw.line(screen, (r, g, b), (0, y_coord), (884, y_coord))

        # 2. Montañas (Mountain silhouettes)
        far_pts = [
            (0, 360),
            (80, 260),
            (180, 300),
            (290, 220),
            (380, 290),
            (480, 240),
            (600, 310),
            (720, 250),
            (884, 360)
        ]
        pygame.draw.polygon(screen, (140, 165, 195), far_pts)

        near_pts = [
            (0, 360),
            (50, 290),
            (140, 330),
            (240, 260),
            (350, 320),
            (450, 280),
            (540, 340),
            (660, 270),
            (780, 330),
            (884, 360)
        ]
        pygame.draw.polygon(screen, (105, 130, 160), near_pts)

        # 3. Bosque lejano (Pine tree silhouettes)
        tree_color = (40, 75, 55)
        for tx in range(-10, 894, 25):
            h_var = 30 + (tx % 7) * 4
            pygame.draw.polygon(screen, tree_color, [
                (tx, 360 - h_var),
                (tx - 15, 360),
                (tx + 15, 360)
            ])
            pygame.draw.polygon(screen, (32, 63, 46), [
                (tx + 12, 360 - h_var + 6),
                (tx - 3, 360),
                (tx + 27, 360)
            ])

        # 5. Suelo (Ground base + grass tiles)
        # Base dirt
        pygame.draw.rect(screen, (75, 50, 35), (0, 360, 884, 100))
        # Grass tiles from mountain asset
        if self.mountain_grass_tile:
            for x in range(0, 884, 32):
                screen.blit(self.mountain_grass_tile, (x, 360))
        else:
            pygame.draw.rect(screen, (48, 110, 36), (0, 360, 884, 10))
            pygame.draw.rect(screen, (60, 145, 45), (0, 360, 884, 4))
            
        # Ground details
        rng_det = random.Random(45)
        for _ in range(15):
            rx = rng_det.randint(0, 884)
            ry = rng_det.randint(392, 450)
            pygame.draw.line(screen, (80, 180, 60), (rx, ry), (rx - 2, ry - 6), 2)
            pygame.draw.line(screen, (80, 180, 60), (rx, ry), (rx + 2, ry - 5), 2)
            px = rng_det.randint(0, 884)
            py = rng_det.randint(392, 450)
            pygame.draw.circle(screen, (110, 110, 110), (px, py), 3)
            pygame.draw.circle(screen, (80, 80, 80), (px, py), 2)

        # 4. Árboles frontales (Front decorations)
        for key, wx, wy in self.arena_decorations:
            img = self.dec_imgs.get(key)
            if img is not None:
                iw, ih = img.get_size()
                screen.blit(img, (wx - iw//2, wy - ih))

        # ── Top Left: Stats Héroe ─────────────────────────────────────────
        pygame.draw.rect(screen, (15, 20, 35), (0, 0, 220, 120))
        pygame.draw.rect(screen, (80, 120, 200), (0, 0, 220, 120), 2)
        screen.blit(font_medium.render(f"{self.hero.name} NV {self.hero.hero_level}", True, (100, 180, 255)), (10, 8))
        screen.blit(font_small.render(f"HP: {self.hero.hp}/{self.hero.max_hp}", True, (255, 100, 100)), (10, 36))
        pygame.draw.rect(screen, (100, 0, 0), (100, 41, 100, 10))
        hp_ratio = max(0, self.hero.hp / self.hero.max_hp)
        pygame.draw.rect(screen, (50, 200, 100), (100, 41, int(100*hp_ratio), 10))
        screen.blit(font_small.render(f"MP: {self.hero.mp}/{self.hero.max_mp}", True, (100, 100, 255)), (10, 62))
        pygame.draw.rect(screen, (0, 0, 100), (100, 67, 100, 10))
        mp_ratio = max(0, self.hero.mp / self.hero.max_mp)
        pygame.draw.rect(screen, (80, 80, 255), (100, 67, int(100*mp_ratio), 10))
        screen.blit(font_small.render(f"XP: {self.hero.hero_exp}/{self.hero.exp_to_next_level}", True, (255, 215, 0)), (10, 88))
        pygame.draw.rect(screen, (20, 15, 40), (100, 93, 100, 10))
        xp_ratio = max(0.0, min(1.0, self.hero.hero_exp / self.hero.exp_to_next_level))
        pygame.draw.rect(screen, (200, 160, 45), (100, 93, int(100*xp_ratio), 10))

        # ── Top Right: Stats Enemigo ──────────────────────────────────────
        pygame.draw.rect(screen, (35, 15, 15), (664, 0, 220, 120))
        pygame.draw.rect(screen, (200, 80, 80), (664, 0, 220, 120), 2)
        screen.blit(font_medium.render(self.enemy.name, True, (255, 120, 100)), (674, 10))
        screen.blit(font_small.render(f"HP: {self.enemy.hp}/{self.enemy.max_hp}", True, (255, 100, 100)), (674, 50))
        pygame.draw.rect(screen, (100, 0, 0), (744, 55, 100, 10))
        ehp_ratio = max(0, self.enemy.hp / self.enemy.max_hp)
        pygame.draw.rect(screen, (220, 60, 60), (744, 55, int(100*ehp_ratio), 10))

        # ── Top Center: Temporizador ──────────────────────────────────────
        pygame.draw.rect(screen, (20, 20, 35), (252, 0, 380, 120))
        pygame.draw.rect(screen, (100, 80, 200), (252, 0, 380, 120), 2)
        t_surf = font_medium.render(f"TIEMPO: {int(self.timer)}s", True, (255, 200, 0))
        screen.blit(t_surf, (442 - t_surf.get_width() // 2, 30))
        pygame.draw.rect(screen, (50, 50, 50), (292, 70, 300, 20))
        timer_ratio = max(0, self.timer / 40.0)
        pygame.draw.rect(screen, (200, 160, 50), (292, 70, int(300*timer_ratio), 20))

        # ── Capa 6: Personajes y Sombras ────────────────────────────────────
        hero_sx = 240
        hero_sy = 360
        
        # Draw shadow under hero
        hero_shadow_w = 64
        hero_shadow_h = 16
        hero_shadow = pygame.Surface((hero_shadow_w, hero_shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(hero_shadow, (0, 0, 0, 100), (0, 0, hero_shadow_w, hero_shadow_h))
        screen.blit(hero_shadow, (hero_sx - hero_shadow_w//2, hero_sy - hero_shadow_h//2))
        
        # Smooth bobbing using continuous time
        t_ticks = pygame.time.get_ticks() / 1000.0
        hero_bob = int(math.sin(t_ticks * 3.5) * 3)
        
        if self._battle_hero_frames:
            hf   = self._battle_hero_frames[self._battle_hero_idx % len(self._battle_hero_frames)]
            hrect = hf.get_rect(midbottom=(hero_sx, hero_sy + hero_bob + 8))
            screen.blit(hf, hrect)
        else:
            self.hero.draw_sprite(screen, hero_sx, hero_sy + hero_bob)

        # Enemy
        enemy_sx = 620
        enemy_sy = 360
        
        # Draw shadow under enemy
        if self.enemy.level % 2 == 0:  # Treant
            enemy_shadow_w = 72
            enemy_shadow_h = 16
        else:  # Mole
            enemy_shadow_w = 56
            enemy_shadow_h = 12
        enemy_shadow = pygame.Surface((enemy_shadow_w, enemy_shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(enemy_shadow, (0, 0, 0, 100), (0, 0, enemy_shadow_w, enemy_shadow_h))
        screen.blit(enemy_shadow, (enemy_sx - enemy_shadow_w//2, enemy_sy - enemy_shadow_h//2))
        
        enemy_bob = int(math.sin(t_ticks * 3.0 + 1.0) * 3)
        
        if self._battle_enemy_frames:
            ef    = self._battle_enemy_frames[self._battle_enemy_idx % len(self._battle_enemy_frames)]
            ef_flipped = pygame.transform.flip(ef, True, False)
            erect = ef_flipped.get_rect(midbottom=(enemy_sx, enemy_sy + enemy_bob + 8))
            screen.blit(ef_flipped, erect)
        else:
            self.enemy.draw_sprite(screen, enemy_sx, enemy_sy + enemy_bob)

        # Zona inferior: Mensajes, Cartas, Dado (884x180) en y=460
        pygame.draw.rect(screen, (10, 8, 18), (0, 460, 884, 180)) 
        pygame.draw.line(screen, (80, 60, 160), (0, 460), (884, 460), 2)
        
        # Log de mensajes con scroll automático y word-wrap dinámico
        self.wrapped_log = []
        for msg in self.message_log:
            self.wrapped_log.extend(self._wrap_text_bs(msg, font_small, 305))
            
        max_scroll = max(0, len(self.wrapped_log) - 6)
        if not hasattr(self, 'prev_wrapped_len') or len(self.wrapped_log) > self.prev_wrapped_len:
            self.log_scroll = max_scroll
        self.prev_wrapped_len = len(self.wrapped_log)
        self.log_scroll = max(0, min(self.log_scroll, max_scroll))
        
        pygame.draw.rect(screen, (8, 8, 15), (10, 470, 320, 160))
        pygame.draw.rect(screen, (60, 60, 100), (10, 470, 320, 160), 1)
        visible = self.wrapped_log[self.log_scroll:self.log_scroll+6]
        for i, msg in enumerate(visible):
            screen.blit(font_small.render(msg, True, (200, 200, 200)), (15, 475 + i*25))

        if len(self.wrapped_log) > 6:
            scroll_text = font_small.render(f"↑↓ {self.log_scroll+1}/{len(self.wrapped_log)}", True, (120, 120, 180))
            screen.blit(scroll_text, (15, 610))

        # Dado / Botones de lanzar
        if self.selected_dice_count == 0 and self.actions_left == 0 and not self.hand and self.turn == "HERO":
            # Mostrar opciones antes de lanzar
            btn_single = pygame.Rect(487, 485, 240, 45)
            btn_double = pygame.Rect(487, 545, 240, 45)
            
            mx, my = pygame.mouse.get_pos()
            hover_single = btn_single.collidepoint(mx, my)
            hover_double = btn_double.collidepoint(mx, my)
            
            bg_single = (50, 35, 90) if hover_single else (30, 20, 60)
            border_single = (150, 120, 255) if hover_single else (100, 80, 200)
            
            bg_double = (50, 35, 90) if hover_double else (30, 20, 60)
            border_double = (150, 120, 255) if hover_double else (100, 80, 200)
            
            # Dibujar botón de dado único
            pygame.draw.rect(screen, bg_single, btn_single, border_radius=6)
            pygame.draw.rect(screen, border_single, btn_single, 2, border_radius=6)
            txt_single = font_small.render("Lanzar Dado", True, (255, 255, 255))
            screen.blit(txt_single, (btn_single.centerx - txt_single.get_width() // 2, btn_single.centery - txt_single.get_height() // 2))
            
            # Dibujar botón de doble dado
            pygame.draw.rect(screen, bg_double, btn_double, border_radius=6)
            pygame.draw.rect(screen, border_double, btn_double, 2, border_radius=6)
            txt_double = font_small.render("Lanzar Doble Dado", True, (255, 255, 255))
            screen.blit(txt_double, (btn_double.centerx - txt_double.get_width() // 2, btn_double.centery - txt_double.get_height() // 2))
        else:
            # Dibujar los dados según la selección
            if self.selected_dice_count == 1:
                # Dibujar un dado centrado en el panel de dados (x=381) usando font_medium
                self.dice1.draw(screen, font_medium)
            elif self.selected_dice_count == 2:
                # Dibujar Dado 1 (Normal) en x=345
                self.dice1.draw(screen, font_medium)
                
                # Dibujar Dado 2 (Riesgo) en x=417
                self.dice2.draw(screen, font_medium, bg_color=(150, 40, 40), border_color=(255, 100, 100), text_color=(255, 255, 255))
                
                # Mostrar los resultados y total encima de los dados
                if self.dice_processed:
                    txt1 = font_small.render(f"D1: {self.dice1.value}", True, (200, 200, 255))
                    txt2 = font_small.render(f"D2: {self.dice2.value}", True, (255, 180, 180))
                    txt_tot = font_small.render(f"Total: {self.dice1.value + self.dice2.value}", True, (255, 215, 0))
                    
                    screen.blit(txt1, (340, 480))
                    screen.blit(txt2, (415, 480))
                    screen.blit(txt_tot, (405 - txt_tot.get_width() // 2, 498))
                    
                    if hasattr(self, 'double_roll_effect_text') and self.double_roll_effect_text:
                        if "Bajo" in self.double_roll_effect_text:
                            col = (255, 100, 100)
                        elif "Alto" in self.double_roll_effect_text or "LEGENDARIO" in self.double_roll_effect_text:
                            col = (100, 255, 100)
                        else:
                            col = (220, 220, 220)
                        txt_eff = font_small.render(self.double_roll_effect_text, True, col)
                        screen.blit(txt_eff, (405 - txt_eff.get_width() // 2, 582))

        # Cartas generadas por el dado
        self.update_card_rects()
        for i, card in enumerate(self.hand):
            # Verificamos hover
            mouse_pos = pygame.mouse.get_pos()
            is_hovered = False
            if self.actions_left > 0 and card.rect.collidepoint(mouse_pos):
                is_hovered = True
                
            # Modo combo parpadea
            is_combo_highlight = self.combo_mode
            
            card.draw(screen, card.rect.x, card.rect.y, font_small, font_small, 
                     is_selected=(is_hovered or is_combo_highlight), 
                     blink_timer=self.blink_timer,
                     width=card.rect.width,
                     height=card.rect.height)

        # Botón de Pausa en la esquina superior derecha del área de juego
        btn = pygame.Rect(834, 5, 45, 30)
        pygame.draw.rect(screen, (40, 30, 70), btn, border_radius=6)
        pygame.draw.rect(screen, (150, 120, 255), btn, 2, border_radius=6)
        screen.blit(font_small.render("II", True, (255, 255, 255)), (846, 10))

        # Panel de Pausa
        if self.show_pause_menu:
            pygame.draw.rect(screen, (15, 10, 30), (192, 180, 500, 280))
            pygame.draw.rect(screen, (100, 80, 200), (192, 180, 500, 280), 2)
            
            title = font_large.render("PAUSA", True, (255, 200, 0))
            screen.blit(title, (442 - title.get_width() // 2, 200))
            
            name_surf = font_medium.render(f"Jugador: {self.hero.name}", True, (180, 180, 220))
            screen.blit(name_surf, (442 - name_surf.get_width() // 2, 238))
            
            buttons = [
                ("REANUDAR", 270),
                ("EMPEZAR DE NUEVO", 330),
                ("SALIR AL MENÚ", 390)
            ]
            for text_str, btn_y in buttons:
                btn_rect = pygame.Rect(292, btn_y - 5, 300, 40)
                pygame.draw.rect(screen, (30, 20, 60), btn_rect)
                pygame.draw.rect(screen, (100, 80, 200), btn_rect, 2)
                
                txt_surf = font_small.render(text_str, True, (255, 255, 255))
                screen.blit(txt_surf, (442 - txt_surf.get_width() // 2, btn_rect.centery - txt_surf.get_height() // 2))
