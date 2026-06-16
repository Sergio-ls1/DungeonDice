import pygame
import math
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


_font_cache = {}
def get_card_font(size):
    if size not in _font_cache:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(base_dir, "..", "..", "assets", "fonts", "pixel.ttf")
        res_font = resource_path(font_path)
        if os.path.exists(res_font):
            _font_cache[size] = pygame.font.Font(res_font, size)
        else:
            _font_cache[size] = pygame.font.SysFont("courier", size, bold=True)
    return _font_cache[size]

def draw_star(surface, center, r_outer, r_inner, color):
    points = []
    import math
    for i in range(10):
        angle = i * math.pi / 5 - math.pi / 2
        r = r_outer if i % 2 == 0 else r_inner
        x = center[0] + r * math.cos(angle)
        y = center[1] + r * math.sin(angle)
        points.append((x, y))
    pygame.draw.polygon(surface, color, points)

class Card:
    def __init__(self, name, level, card_type, value, effect, description, color):
        self.name = name
        self.level = level
        self.card_type = card_type  # 'attack', 'strong', 'heal', 'special'
        self.value = value
        self.effect = effect
        self.description = description
        self.color = color
        self.rect = pygame.Rect(0, 0, 115, 160)  # Dimensiones base de la carta

    def draw(self, surface, x, y, font_title, font_desc, is_selected=False, blink_timer=0, width=115, height=160):
        self.rect.width = width
        self.rect.height = height
        self.rect.x = x
        self.rect.y = y
        
        # Mapeo de colores según el tipo
        colors_map = {
            "attack": {
                "border": (230, 50, 50),       # Rojo brillante
                "bg": (30, 15, 15),            # Rojo muy oscuro
                "header": (80, 20, 20),        # Rojo oscuro
                "text": (255, 100, 100)        # Rojo claro llamativo
            },
            "strong": {
                "border": (240, 120, 20),      # Naranja brillante
                "bg": (35, 20, 15),            # Naranja muy oscuro
                "header": (95, 45, 15),        # Naranja oscuro
                "text": (255, 160, 50)         # Naranja claro llamativo
            },
            "heal": {
                "border": (50, 200, 80),       # Verde brillante
                "bg": (15, 30, 20),            # Verde muy oscuro
                "header": (20, 70, 35),        # Verde oscuro
                "text": (100, 255, 120)        # Verde claro llamativo
            },
            "special": {
                "border": (160, 90, 240),      # Violeta brillante
                "bg": (25, 15, 35),            # Violeta muy oscuro
                "header": (65, 30, 100),       # Violeta oscuro
                "text": (200, 140, 255)        # Violeta claro llamativo
            }
        }
        
        cfg = colors_map.get(self.card_type, colors_map["special"])
        
        # 1. Fondo de la carta
        br = max(4, int(width * (8 / 115)))
        pygame.draw.rect(surface, cfg["bg"], self.rect, border_radius=br)
        
        # 2. Fondo de la cabecera
        header_h = int(height * (28 / 160))
        header_rect = pygame.Rect(x + 2, y + 2, width - 4, header_h)
        header_br = max(3, int(width * (6 / 115)))
        pygame.draw.rect(surface, cfg["header"], header_rect, border_radius=header_br)
        
        # 3. Borde iluminado en hover (is_selected = True)
        border_color = cfg["border"]
        border_width = max(1, int(width * (2 / 115)))
        if is_selected:
            pulse = (math.sin(blink_timer * 10) + 1) / 2
            border_color = (
                min(255, int(cfg["border"][0] + (255 - cfg["border"][0]) * pulse * 0.6)),
                min(255, int(cfg["border"][1] + (255 - cfg["border"][1]) * pulse * 0.6)),
                min(255, int(cfg["border"][2] + (255 - cfg["border"][2]) * pulse * 0.6))
            )
            border_width = max(2, int(width * (4 / 115)))
        pygame.draw.rect(surface, border_color, self.rect, border_width, border_radius=br)
        
        # 4. Nombre arriba (cortar con "..." si es largo)
        title_size = max(8, int(height * (14 / 160)))
        title_font = get_card_font(title_size)
        name_text = self.name
        max_title_w = width - 10
        while title_font.size(name_text)[0] > max_title_w and len(name_text) > 3:
            name_text = name_text[:-1]
        if name_text != self.name:
            name_text = name_text[:-2] + "..."
            
        title_surf = title_font.render(name_text, True, (255, 255, 255))
        tx = x + (width - title_surf.get_width()) // 2
        ty = y + 2 + (header_h - title_surf.get_height()) // 2
        surface.blit(title_surf, (tx, ty))
        
        # 5. Valor en el centro (fuente grande, color llamativo)
        val_size = max(16, int(height * (36 / 160)))
        y_val_start = y + 2 + header_h
        y_desc_start = y + int(height * (88 / 160))
        if self.value <= 0:
            cx = x + width // 2
            cy = y_val_start + (y_desc_start - y_val_start) // 2
            r_outer = val_size // 2
            r_inner = int(r_outer // 2.2)
            draw_star(surface, (cx, cy), r_outer, r_inner, cfg["text"])
        else:
            val_text = str(self.value)
            large_font = get_card_font(val_size)
            val_surf = large_font.render(val_text, True, cfg["text"])
            vx = x + (width - val_surf.get_width()) // 2
            vy = y_val_start + (y_desc_start - y_val_start - val_surf.get_height()) // 2
            surface.blit(val_surf, (vx, vy))
        
        # 6. Descripción abajo (ajuste dinámico de líneas)
        desc_size = max(7, int(height * (12 / 160)))
        desc_font = get_card_font(desc_size)
        max_desc_w = width - 12
        words = self.description.split(' ')
        lines = []
        current_line = ""
        for word in words:
            if desc_font.size(word)[0] > max_desc_w:
                for char in word:
                    if desc_font.size(current_line + char)[0] <= max_desc_w:
                        current_line += char
                    else:
                        lines.append(current_line.strip())
                        current_line = char
                current_line += " "
            else:
                test_line = current_line + word
                if desc_font.size(test_line)[0] <= max_desc_w:
                    current_line = test_line + " "
                else:
                    lines.append(current_line.strip())
                    current_line = word + " "
        if current_line:
            lines.append(current_line.strip())
            
        lines = lines[:4]
        y_offset = y + int(height * (88 / 160))
        line_height = desc_font.get_height()
        for line in lines:
            desc_surf = desc_font.render(line, True, (220, 220, 220))
            dx = x + (width - desc_surf.get_width()) // 2
            surface.blit(desc_surf, (dx, y_offset))
            y_offset += line_height + 2


def get_cards_for_roll(dice_result):
    """Retorna una lista de 4 cartas dependiendo del resultado del dado (1 al 6)."""
    # Definición de colores para los bordes
    COLOR_ATTACK = (255, 50, 50)    # Rojo
    COLOR_STRONG = (255, 140, 0)    # Naranja
    COLOR_HEAL = (50, 255, 50)      # Verde
    COLOR_SPECIAL = (255, 215, 0)   # Dorado

    if dice_result == 1:
        return [
            Card("Ataque Básico", 1, "attack", 3, None, "Causa 3 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 1, "strong", 5, None, "Causa 5 de daño.", COLOR_STRONG),
            Card("Curación", 1, "heal", 4, None, "Cura 4 HP.", COLOR_HEAL),
            Card("Tropiezo", 1, "special", 0, "skip_both", "Ambos pierden 1 turno.", COLOR_SPECIAL)
        ]
    elif dice_result == 2:
        return [
            Card("Ataque Básico", 2, "attack", 6, None, "Causa 6 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 2, "strong", 10, None, "Causa 10 de daño.", COLOR_STRONG),
            Card("Curación", 2, "heal", 8, None, "Cura 8 HP.", COLOR_HEAL),
            Card("Escudo Frágil", 2, "special", 0, "shield_30", "Reduce el próximo daño recibido en 30%.", COLOR_SPECIAL)
        ]
    elif dice_result == 3:
        return [
            Card("Ataque Básico", 3, "attack", 12, None, "Causa 12 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 3, "strong", 18, None, "Causa 18 de daño.", COLOR_STRONG),
            Card("Curación", 3, "heal", 15, None, "Cura 15 HP.", COLOR_HEAL),
            Card("Veneno Leve", 3, "special", 0, "poison_4_2", "El enemigo pierde 4 HP por turno durante 2 turnos.", COLOR_SPECIAL)
        ]
    elif dice_result == 4:
        return [
            Card("Ataque Básico", 4, "attack", 20, None, "Causa 20 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 4, "strong", 30, None, "Causa 30 de daño.", COLOR_STRONG),
            Card("Curación", 4, "heal", 25, None, "Cura 25 HP.", COLOR_HEAL),
            Card("Escudo Sólido", 4, "special", 0, "shield_60", "Bloquea el 60% del próximo ataque enemigo.", COLOR_SPECIAL)
        ]
    elif dice_result == 5:
        return [
            Card("Ataque Básico", 5, "attack", 32, None, "Causa 32 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 5, "strong", 48, None, "Causa 48 de daño.", COLOR_STRONG),
            Card("Curación", 5, "heal", 40, "regen_5_2", "Cura 40 HP y 5 HP extra por 2 turnos.", COLOR_HEAL),
            Card("Golpe Paralizante", 5, "special", 0, "stun_1", "El enemigo pierde su próximo turno.", COLOR_SPECIAL)
        ]
    elif dice_result == 6:
        return [
            Card("Ataque Básico", 6, "attack", 50, None, "Causa 50 de daño.", COLOR_ATTACK),
            Card("Ataque Fuerte", 6, "strong", 75, "ignore_def", "Causa 75 daño. Ignora DEF enemiga.", COLOR_STRONG),
            Card("Curación", 6, "heal", 60, "restore_10_mp", "Cura 60 HP y restaura 10 MP.", COLOR_HEAL),
            Card("COMBO FINAL", 6, "special", 0, "combo_2", "Selecciona 2 cartas. Ambas se ejecutan en este turno.", COLOR_SPECIAL)
        ]
    
    return []
